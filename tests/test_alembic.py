"""
The default database used for debriefly is a local SQLite database.
In production, the database is a PostgreSQL database.

This test module helps to ensure that alembic will behave itself when used in
both scenarios, and should be invoked with as many instances of the DB_URL
envvar as need to be tested, e.g.:

DB_URL=sqlite:///test.db pytest tests/test_alembic.py
DB_URL=postgresql://user:pass@host/dbname pytest tests/test_alembic.py

The sqlite:// case is run if no DB_URL is provided.

Why is this useful?
-------------------

We have seen that `reflex db makemigrations` sometimes spits out
engine-specific stuff like:

sa.Column('myts', sa.DateTime(timezone=True), server_default=sa.text('now()')),

while a version that would work for both SQLite and PostgreSQL would be:

sa.Column('myts', sa.DateTime(timezone=True), server_default=sa.func.now()),

These adjustments are currently made in the alembic/ folder manually, but there
is probably a way to run `reflex db makemigrations` etc. in an engine-agnostic
mode.
"""

import os
from pathlib import Path
from alembic import command
from alembic.config import Config


THIS_DIR = Path(__file__).parent


def test_alembic_init_upgrade_downgrade(tmp_path):
    if db_url := os.getenv("DB_URL") is None:
        db_url = str(tmp_path / "test.db")
        db_url = f"sqlite:///{db_url}"

    alembic_cfg = Config()

    alembic_cfg.set_main_option("script_location", str(THIS_DIR / "../alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
