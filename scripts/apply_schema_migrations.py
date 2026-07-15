"""Apply the committed Alembic chain using Reflex's configured database URL.

This small runner is primarily used by the Clerk rollback image. Calling
Alembic directly avoids comparing the upgraded schema to the older Clerk
image's ORM metadata, which intentionally does not declare the additive local
authentication tables.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from reflex.config import get_config
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    """Return an Alembic config bound to the application's actual database."""

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # ConfigParser treats percent signs in URL-encoded credentials as
    # interpolation unless they are doubled.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def main() -> None:
    database_url = (get_config().db_url or "").strip()
    if not database_url:
        raise RuntimeError("Database URL is not configured")
    config = alembic_config(database_url)
    command.upgrade(config, "head")

    expected_heads = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            actual_heads = set(
                MigrationContext.configure(connection).get_current_heads()
            )
    finally:
        engine.dispose()
    if actual_heads != expected_heads:
        raise RuntimeError(
            "Database migration verification failed: "
            f"expected {sorted(expected_heads)!r}, found {sorted(actual_heads)!r}"
        )
    print(f"Database schema is current at {', '.join(sorted(actual_heads))}.")


if __name__ == "__main__":
    main()
