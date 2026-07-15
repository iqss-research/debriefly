"""Database configuration helpers shared by Reflex and tests."""

from collections.abc import Mapping
from urllib.parse import urlsplit


def database_url_from_env(env: Mapping[str, str]) -> str:
    """Resolve the database URL from current and legacy environment variables."""
    require_explicit_url = env.get(
        "DEBRIEFLY_REQUIRE_DATABASE_URL",
        "",
    ).strip().casefold() in {"1", "true", "yes", "on"}
    explicit_url = env.get("DB_URL", "").strip()
    if explicit_url:
        if (
            require_explicit_url
            and urlsplit(explicit_url).scheme.split("+", 1)[0] != "postgresql"
        ):
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
        return "sqlite:///debriefly.db"

    missing_values = [name for name, value in legacy_values.items() if not value]
    if missing_values:
        missing = ", ".join(missing_values)
        raise ValueError(
            "Incomplete legacy database configuration. Set DB_URL or provide "
            f"DB_USER, DB_PASS, DB_NAME, and DB_HOST. Missing: {missing}."
        )

    return (
        "postgresql://"
        f"{legacy_values['DB_USER']}:{legacy_values['DB_PASS']}"
        f"@{legacy_values['DB_HOST']}/{legacy_values['DB_NAME']}"
    )
