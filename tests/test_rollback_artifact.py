import importlib.util
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
LOCAL_AUTH_REVISION = "f6b7c8d9e0a1"

_SPEC = importlib.util.spec_from_file_location(
    "apply_schema_migrations",
    ROOT / "scripts/apply_schema_migrations.py",
)
assert _SPEC is not None and _SPEC.loader is not None
apply_schema_migrations = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(apply_schema_migrations)

_HEAD_SPEC = importlib.util.spec_from_file_location(
    "check_migration_head",
    ROOT / "scripts/check_migration_head.py",
)
assert _HEAD_SPEC is not None and _HEAD_SPEC.loader is not None
check_migration_head = importlib.util.module_from_spec(_HEAD_SPEC)
_HEAD_SPEC.loader.exec_module(check_migration_head)


def test_schema_runner_applies_the_committed_head(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'rollback.db'}"
    monkeypatch.setattr(
        apply_schema_migrations,
        "get_config",
        lambda: SimpleNamespace(db_url=database_url),
    )

    apply_schema_migrations.main()

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            LOCAL_AUTH_REVISION
        )
    engine.dispose()


def test_schema_runner_preserves_percent_encoded_database_urls():
    database_url = "postgresql://user:pass%25word@db.example/debriefly"

    config = apply_schema_migrations.alembic_config(database_url)

    # get_main_option exercises ConfigParser interpolation on the value set by
    # the helper.
    assert isinstance(config, Config)
    assert config.get_main_option("sqlalchemy.url") == database_url


def test_release_has_one_expected_migration_head():
    assert check_migration_head.migration_heads(ROOT / "alembic/versions") == {
        LOCAL_AUTH_REVISION
    }


def test_clerk_rollback_image_keeps_clerk_code_and_fails_on_migration_error():
    dockerfile = (ROOT / "Dockerfile.clerk-rollback").read_text(encoding="utf-8")

    assert "FROM ${CLERK_BASE_IMAGE}" in dockerfile
    assert "ENV DEBRIEFLY_REQUIRE_DATABASE_URL=true" in dockerfile
    assert '__version__ = "0.8.0"' in dockerfile
    assert "import reflex_clerk as clerk" in dockerfile
    assert "python3 -c 'import reflex_clerk'" in dockerfile
    assert "COPY alembic/ /app/alembic/" in dockerfile
    assert "COPY rxconfig.py /app/rxconfig.py" in dockerfile
    assert "COPY src/debriefly/database.py" in dockerfile
    assert "COPY scripts/check_migration_head.py" in dockerfile
    assert "COPY scripts/apply_schema_migrations.py" in dockerfile
    assert LOCAL_AUTH_REVISION in dockerfile

    startup = dockerfile.rsplit("\nCMD ", 1)[1]
    assert "set -eu" in startup
    assert "python3 scripts/apply_schema_migrations.py" in startup
    assert "||" not in startup


def test_production_image_requires_postgresql_and_uses_direct_migrations():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV DEBRIEFLY_REQUIRE_DATABASE_URL=true" in dockerfile
    startup = dockerfile.rsplit("\nCMD ", 1)[1]
    assert "set -eu" in startup
    assert "python3 scripts/apply_schema_migrations.py" in startup
    assert "||" not in startup


def test_docker_context_excludes_local_databases_and_migration_exports():
    patterns = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {
        ".git/",
        "*.csv",
        "*.db",
        "*.db-*",
        "*.sqlite",
        "*.sqlite-*",
        "*.sqlite3",
        "*.sqlite3-*",
    } <= patterns
