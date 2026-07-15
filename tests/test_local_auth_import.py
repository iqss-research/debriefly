from datetime import datetime, timezone
import hashlib
import hmac

from debriefly.reflex.backend.models import (
    AuthToken,
    Form,
    LocalCredential,
    User,
    UserIdentity,
    UserOpenAISettings,
)
from sqlmodel import Session, SQLModel, create_engine, select
from scripts.import_clerk_users import (
    ClerkUserRow,
    apply_import_plan,
    build_import_plan,
    read_clerk_csv,
    users_requiring_setup_tokens,
)


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def _verified_row(user_id: str = "user_owner") -> ClerkUserRow:
    now = datetime.now(timezone.utc)
    return ClerkUserRow(
        line_number=2,
        clerk_user_id=user_id,
        email="Owner@Example.com",
        email_normalized="owner@example.com",
        email_verified_at=now,
    )


def test_import_is_idempotent_and_preserves_ownership(tmp_path):
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc)
    row = _verified_row()
    token_secret = "test-secret-that-is-at-least-32-bytes-long"

    with Session(engine) as session:
        session.add(User(user_id=row.clerk_user_id))
        session.add(
            Form(
                id=101,
                name="Owned survey",
                code="owned-survey",
                user_id=row.clerk_user_id,
            )
        )
        session.add(
            UserOpenAISettings(
                user_id=row.clerk_user_id,
                api_key="test-key",
                model="gpt-4o-mini",
            )
        )
        session.commit()

        plan = build_import_plan(
            session,
            [row],
            issuer="https://clerk.example.test",
        )
        assert plan.conflicts == []
        assert plan.users_to_create == 0
        assert plan.identities_to_create == 1
        assert plan.credentials_to_create == 1

        setup_users = users_requiring_setup_tokens(session, plan, now=now)
        assert setup_users == {row.clerk_user_id}
        setup_tokens = apply_import_plan(
            session,
            plan,
            issuer="https://clerk.example.test",
            setup_user_ids=setup_users,
            setup_token_hours=48,
            token_secret=token_secret,
            now=now,
        )
        session.commit()

        assert session.get(Form, 101).user_id == row.clerk_user_id
        assert (
            session.get(UserOpenAISettings, row.clerk_user_id).user_id
            == row.clerk_user_id
        )
        assert session.get(User, row.clerk_user_id).email_normalized == (
            "owner@example.com"
        )
        assert session.get(LocalCredential, row.clerk_user_id).password_hash is None
        assert len(setup_tokens) == 1
        saved_token = session.exec(select(AuthToken)).one()
        expected_digest = hmac.new(
            token_secret.encode("utf-8"),
            setup_tokens[0].raw_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert saved_token.token_digest == expected_digest
        assert saved_token.token_digest != setup_tokens[0].raw_token

        second_plan = build_import_plan(
            session,
            [row],
            issuer="https://clerk.example.test",
        )
        assert second_plan.conflicts == []
        assert second_plan.identities_to_create == 0
        assert second_plan.credentials_to_create == 0
        assert users_requiring_setup_tokens(session, second_plan, now=now) == set()
        assert len(session.exec(select(UserIdentity)).all()) == 1
        assert len(session.exec(select(AuthToken)).all()) == 1


def test_plan_rejects_orphaned_form_ownership(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            Form(
                name="Orphaned survey",
                code="orphaned-survey",
                user_id="missing-owner",
            )
        )
        session.commit()

        plan = build_import_plan(
            session,
            [_verified_row()],
            issuer="https://clerk.example.test",
        )

    assert not plan.can_commit
    assert any("forms reference missing users" in error for error in plan.conflicts)


def test_csv_rejects_duplicate_verified_email(tmp_path):
    csv_path = tmp_path / "clerk.csv"
    csv_path.write_text(
        "clerk_user_id,primary_email,email_verified\n"
        "user_one,owner@example.com,true\n"
        "user_two,OWNER@example.com,true\n",
        encoding="utf-8",
    )

    try:
        read_clerk_csv(csv_path)
    except ValueError as exc:
        assert "verified email duplicates line" in str(exc)
    else:
        raise AssertionError("duplicate verified email should be rejected")


def test_password_hash_is_not_stored_on_serialized_user_model():
    assert "password_hash" not in User.get_fields()
    assert "password_hash" in LocalCredential.get_fields()
