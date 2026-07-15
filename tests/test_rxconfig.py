import pytest

from debriefly.database import database_url_from_env


def test_explicit_db_url_is_honored_without_db_name():
    db_url = "postgresql://explicit-user:explicit-pass@db.example/debriefly"

    assert database_url_from_env({"DB_URL": db_url}) == db_url


def test_explicit_db_url_takes_precedence_over_legacy_configuration():
    db_url = "postgresql://explicit-user:explicit-pass@db.example/debriefly"
    env = {
        "DB_URL": db_url,
        "DB_USER": "legacy-user",
        "DB_PASS": "legacy-pass",
        "DB_HOST": "legacy-db.example",
        "DB_NAME": "legacy-debriefly",
    }

    assert database_url_from_env(env) == db_url


def test_complete_legacy_database_configuration_still_works():
    env = {
        "DB_USER": "legacy-user",
        "DB_PASS": "legacy-pass",
        "DB_HOST": "legacy-db.example",
        "DB_NAME": "legacy-debriefly",
    }

    assert database_url_from_env(env) == (
        "postgresql://legacy-user:legacy-pass@legacy-db.example/legacy-debriefly"
    )


def test_incomplete_legacy_database_configuration_fails_fast():
    env = {
        "DB_USER": "legacy-user",
        "DB_PASS": "legacy-pass",
        "DB_HOST": "legacy-db.example",
    }

    with pytest.raises(ValueError, match=r"Missing: DB_NAME"):
        database_url_from_env(env)


def test_empty_database_values_fall_back_to_sqlite():
    env = {
        "DB_URL": "  ",
        "DB_USER": "",
        "DB_PASS": "",
        "DB_HOST": "",
        "DB_NAME": "",
    }

    assert database_url_from_env(env) == "sqlite:///debriefly.db"


def test_production_image_requires_an_explicit_database_url():
    with pytest.raises(ValueError, match=r"DB_URL is required"):
        database_url_from_env(
            {
                "DEBRIEFLY_REQUIRE_DATABASE_URL": "true",
                "DB_USER": "legacy-user",
                "DB_PASS": "legacy-pass",
                "DB_HOST": "legacy-db.example",
                "DB_NAME": "legacy-debriefly",
            }
        )


def test_production_image_rejects_an_explicit_sqlite_url():
    with pytest.raises(ValueError, match=r"must use PostgreSQL"):
        database_url_from_env(
            {
                "DEBRIEFLY_REQUIRE_DATABASE_URL": "true",
                "DB_URL": "sqlite:///debriefly.db",
            }
        )


def test_production_image_accepts_a_postgresql_driver_url():
    database_url = "postgresql+psycopg2://user:pass@db.example/debriefly"

    assert (
        database_url_from_env(
            {
                "DEBRIEFLY_REQUIRE_DATABASE_URL": "true",
                "DB_URL": database_url,
            }
        )
        == database_url
    )
