import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


DEPLOYED_REVISION = "dc22fdc7aa86"
LOCAL_AUTH_REVISION = "f6b7c8d9e0a1"
POSTGRES_TEST_URL_ENV = "DEBRIEFLY_TEST_POSTGRES_URL"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # Match the direct migration runner used by the Clerk rollback image.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def _constraint_columns(inspector, table_name: str) -> dict[str, set[str]]:
    return {
        constraint["name"]: set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _assert_auth_schema(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "user_identity",
        "local_credential",
        "auth_session",
        "auth_token",
    } <= tables

    user_columns = {column["name"]: column for column in inspector.get_columns("user")}
    assert {
        "email_normalized",
        "email_verified_at",
        "status",
        "role",
        "auth_version",
        "created_at",
        "updated_at",
    } <= user_columns.keys()
    for column_name in ("status", "role", "auth_version"):
        assert user_columns[column_name]["nullable"] is False
        assert user_columns[column_name]["default"] is not None
    assert user_columns["created_at"]["nullable"] is True
    assert user_columns["updated_at"]["nullable"] is True

    # This must be a constraint rather than a unique index so the migration
    # matches User.__table_args__ on both supported database engines.
    assert _constraint_columns(inspector, "user")["uq_user_email_normalized"] == {
        "email_normalized"
    }

    assert _constraint_columns(inspector, "user_identity") == {
        "uq_user_identity_provider_issuer_subject": {
            "provider",
            "issuer",
            "subject",
        },
        "uq_user_identity_user_provider_issuer": {
            "user_id",
            "provider",
            "issuer",
        },
    }
    assert _constraint_columns(inspector, "auth_session")[
        "uq_auth_session_token_digest"
    ] == {"token_digest"}
    assert _constraint_columns(inspector, "auth_token")[
        "uq_auth_token_token_digest"
    ] == {"token_digest"}

    for table_name in (
        "user_identity",
        "local_credential",
        "auth_session",
        "auth_token",
    ):
        foreign_keys = inspector.get_foreign_keys(table_name)
        assert len(foreign_keys) == 1
        foreign_key = foreign_keys[0]
        assert foreign_key["constrained_columns"] == ["user_id"]
        assert foreign_key["referred_table"] == "user"
        assert foreign_key["referred_columns"] == ["user_id"]
        assert foreign_key["options"].get("ondelete", "").upper() == "CASCADE"

    expected_indexes = {
        "user_identity": {"ix_user_identity_user_id"},
        "auth_session": {
            "ix_auth_session_user_id",
            "ix_auth_session_expires_at",
        },
        "auth_token": {
            "ix_auth_token_user_id",
            "ix_auth_token_expires_at",
        },
    }
    for table_name, names in expected_indexes.items():
        actual_names = {index["name"] for index in inspector.get_indexes(table_name)}
        assert names <= actual_names


def _exercise_upgrade(database_url: str) -> None:
    config = _config(database_url)
    engine = create_engine(database_url)
    initial_tables = set(inspect(engine).get_table_names())
    # Alembic intentionally leaves its empty version table behind after a
    # downgrade to base. Accept that state so this test can share the
    # disposable PostgreSQL service used by tests/test_alembic.py.
    assert initial_tables <= {
        "alembic_version"
    }, f"Migration test database must be empty: {database_url!r}"
    if "alembic_version" in initial_tables:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 0

    command.upgrade(config, DEPLOYED_REVISION)
    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "user" (user_id, tos_version) '
                "VALUES (:user_id, :tos_version)"
            ),
            {"user_id": "user_owner", "tos_version": "v1"},
        )
        connection.execute(
            text(
                """
                INSERT INTO form
                    (id, name, code, user_id, show_submission_code)
                VALUES
                    (:id, :name, :code, :user_id, :show_submission_code)
                """
            ),
            {
                "id": 123,
                "name": "Survey",
                "code": "survey-code",
                "user_id": "user_owner",
                "show_submission_code": False,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO user_openai_settings (user_id, api_key, model)
                VALUES (:user_id, :api_key, :model)
                """
            ),
            {
                "user_id": "user_owner",
                "api_key": "test-key",
                "model": "gpt-4o-mini",
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT user_id FROM form WHERE id = 123"))
            == "user_owner"
        )
        assert (
            connection.scalar(text("SELECT user_id FROM user_openai_settings"))
            == "user_owner"
        )
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == LOCAL_AUTH_REVISION
        )
    _assert_auth_schema(engine)

    # Exercise the write shape of the released Clerk-backed 0.8.0 models after
    # the additive upgrade. Server defaults must supply every new non-null
    # column that the old application does not know about.
    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO "user" (user_id, tos_version) '
                "VALUES (:user_id, :tos_version)"
            ),
            {"user_id": "rollback_user", "tos_version": "v1"},
        )
        connection.execute(
            text(
                """
                INSERT INTO form
                    (id, name, code, user_id, show_submission_code)
                VALUES
                    (:id, :name, :code, :user_id, :show_submission_code)
                """
            ),
            {
                "id": 124,
                "name": "Rollback survey",
                "code": "rollback-survey",
                "user_id": "rollback_user",
                "show_submission_code": False,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO field
                    (id, name, type_, required, bundled, debriefing,
                     allow_back, prompt, ordering, form_id, scale_min, scale_max)
                VALUES
                    (:id, :name, :type_, :required, :bundled, :debriefing,
                     :allow_back, :prompt, :ordering, :form_id, :scale_min,
                     :scale_max)
                """
            ),
            {
                "id": 125,
                "name": "question",
                "type_": "text",
                "required": False,
                "bundled": False,
                "debriefing": False,
                "allow_back": False,
                "prompt": "",
                "ordering": 0.0,
                "form_id": 124,
                "scale_min": 1,
                "scale_max": 5,
            },
        )
        rollback_user = connection.execute(
            text(
                'SELECT status, role, auth_version FROM "user" '
                "WHERE user_id = :user_id"
            ),
            {"user_id": "rollback_user"},
        ).one()
        assert tuple(rollback_user) == ("active", "user", 1)
        assert connection.scalar(
            text("SELECT interviewer_mode FROM field WHERE id = 125")
        ) in (False, 0)

    command.downgrade(config, DEPLOYED_REVISION)

    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT user_id FROM form WHERE id = 123"))
            == "user_owner"
        )
        assert (
            connection.scalar(text("SELECT user_id FROM user_openai_settings"))
            == "user_owner"
        )
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == DEPLOYED_REVISION
        )

    inspector = inspect(engine)
    assert not {
        "user_identity",
        "local_credential",
        "auth_session",
        "auth_token",
    } & set(inspector.get_table_names())
    assert "email_normalized" not in {
        column["name"] for column in inspector.get_columns("user")
    }

    # Leave an explicitly supplied PostgreSQL test database ready for another
    # migration test in the same CI job.
    command.downgrade(config, "base")
    engine.dispose()


def test_local_auth_upgrade_from_v0_8_0_preserves_ownership(tmp_path):
    _exercise_upgrade(f"sqlite:///{tmp_path / 'migration.db'}")


@pytest.mark.skipif(
    not os.getenv(POSTGRES_TEST_URL_ENV),
    reason=f"Set {POSTGRES_TEST_URL_ENV} to an empty PostgreSQL test database",
)
def test_local_auth_upgrade_on_postgresql():
    """Run the same deployed-to-head migration against an empty PostgreSQL DB."""

    _exercise_upgrade(os.environ[POSTGRES_TEST_URL_ENV])
