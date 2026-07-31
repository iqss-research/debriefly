"""Database configuration helpers shared by Reflex and tests."""

from collections.abc import Mapping
from functools import lru_cache
import os
from urllib.parse import urlsplit

from sqlalchemy.engine import URL


def database_url_from_env(env: Mapping[str, str]) -> str:
    """Resolve the database URL from current and legacy environment variables."""
    require_explicit_url = env.get(
        "DEBRIEFLY_REQUIRE_DATABASE_URL",
        "",
    ).strip().casefold() in {"1", "true", "yes", "on"}
    require_postgresql = env.get(
        "DEBRIEFLY_REQUIRE_POSTGRESQL",
        "",
    ).strip().casefold() in {"1", "true", "yes", "on"}
    explicit_url = env.get("DB_URL", "").strip()
    if explicit_url:
        if (require_explicit_url or require_postgresql) and urlsplit(
            explicit_url
        ).scheme.split("+", 1)[0] != "postgresql":
            raise ValueError("DB_URL must use PostgreSQL in this production image.")
        return explicit_url

    if require_explicit_url:
        raise ValueError(
            "DB_URL is required in this production image. Refusing to use a "
            "pod-local SQLite database or legacy DB_* settings."
        )

    legacy_values = {
        name: env.get(name, "").strip()
        for name in ("DB_USER", "DB_PASS", "DB_NAME", "DB_HOST")
    }
    if not any(legacy_values.values()):
        if require_postgresql:
            raise ValueError(
                "PostgreSQL database configuration is required in this "
                "production image. Set DB_URL or provide DB_USER, DB_PASS, "
                "DB_NAME, and DB_HOST."
            )
        return "sqlite:///debriefly.db"

    missing_values = [name for name, value in legacy_values.items() if not value]
    if missing_values:
        missing = ", ".join(missing_values)
        raise ValueError(
            "Incomplete legacy database configuration. Set DB_URL or provide "
            f"DB_USER, DB_PASS, DB_NAME, and DB_HOST. Missing: {missing}."
        )

    return URL.create(
        "postgresql",
        username=legacy_values["DB_USER"],
        password=legacy_values["DB_PASS"],
        host=legacy_values["DB_HOST"],
        database=legacy_values["DB_NAME"],
    ).render_as_string(hide_password=False)


def install_bounded_reflex_engine() -> None:
    """Make Reflex 0.5.x reuse one bounded SQLAlchemy engine per process.

    Reflex 0.5.10 creates a new engine (and therefore a new connection pool)
    for every ``rx.session()`` call. Under load those short-lived pools can
    collectively consume every PostgreSQL connection. Keep this compatibility
    shim local to the pinned runtime; it can be removed after upgrading to a
    Reflex release whose engine lifecycle is centrally managed.
    """
    import reflex.model as reflex_model
    from reflex.config import get_config
    from sqlmodel import create_engine

    if getattr(reflex_model.get_engine, "_debriefly_bounded", False):
        return

    @lru_cache(maxsize=4)
    def get_bounded_engine(url: str | None = None):
        database_url = url or get_config().db_url
        if database_url is None:
            raise ValueError("No database url configured")

        echo = os.getenv("SQLALCHEMY_ECHO") == "True"
        if database_url.startswith("sqlite"):
            return create_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False},
            )

        return create_engine(
            database_url,
            echo=echo,
            pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "5"))),
            max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "0"))),
            pool_timeout=max(1, int(os.getenv("DB_POOL_TIMEOUT", "30"))),
            pool_recycle=max(30, int(os.getenv("DB_POOL_RECYCLE", "1800"))),
            pool_pre_ping=True,
        )

    get_bounded_engine._debriefly_bounded = True
    reflex_model.get_engine = get_bounded_engine
