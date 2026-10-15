"""Explicit pre-release database preparation; never called on Lambda startup."""

import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migrations and create the temporary UI snapshot table",
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="Delete expired temporary snapshots only"
    )
    args = parser.parse_args()
    if not args.apply and not args.cleanup:
        parser.error(
            "Specify --apply or --cleanup; this command writes to the configured database"
        )
    os.environ["DEBRIEFLY_LAMBDA"] = "true"
    project = Path(__file__).resolve().parents[1]
    os.chdir(project)
    sys.path.insert(0, str(project))
    sys.path.insert(0, str(project / "src"))
    from debriefly.serverless.settings import load_runtime_secret

    load_runtime_secret()
    os.environ.setdefault("DEBRIEFLY_REQUIRE_POSTGRESQL", "true")
    from reflex.config import get_config
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from debriefly.serverless.state import SqlStateStore

    signing_key = os.environ.get("AUTH_SECRET_KEY", "")
    if len(signing_key) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must contain at least 32 characters")
    store = SqlStateStore(
        create_engine(get_config().db_url, poolclass=NullPool), signing_key
    )

    if args.apply:
        runpy.run_path(
            str(project / "scripts/apply_schema_migrations.py"), run_name="__main__"
        )
        store.prepare()
        runpy.run_path(str(project / "scripts/seed_data.py"), run_name="__main__")
        print("Lambda snapshot table is ready.")
    if args.cleanup:
        print(f"Removed {store.cleanup()} expired UI snapshots.")


if __name__ == "__main__":
    main()
