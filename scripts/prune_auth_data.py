"""Prune old local-auth sessions and one-time tokens (dry-run by default)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import dotenv
import reflex as rx
import sqlalchemy as sa

from debriefly.reflex.backend.models import AuthSession, AuthToken


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Keep expired/revoked records this many days (default: 30)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Delete the selected rows (default is dry-run)",
    )
    args = parser.parse_args()
    if not 1 <= args.retention_days <= 3650:
        parser.error("--retention-days must be between 1 and 3650")

    dotenv.load_dotenv()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    session_filter = sa.or_(
        AuthSession.expires_at < cutoff,
        sa.and_(AuthSession.revoked_at.is_not(None), AuthSession.revoked_at < cutoff),
    )
    token_filter = sa.or_(
        AuthToken.expires_at < cutoff,
        sa.and_(AuthToken.used_at.is_not(None), AuthToken.used_at < cutoff),
    )

    with rx.session() as session:
        session_count = session.exec(
            sa.select(sa.func.count()).select_from(AuthSession).where(session_filter)
        ).one()
        token_count = session.exec(
            sa.select(sa.func.count()).select_from(AuthToken).where(token_filter)
        ).one()
        print(f"Old sessions: {session_count}")
        print(f"Old one-time tokens: {token_count}")
        if not args.commit:
            session.rollback()
            print("Dry run complete; no database changes were made.")
            return 0
        session.exec(sa.delete(AuthSession).where(session_filter))
        session.exec(sa.delete(AuthToken).where(token_filter))
        session.commit()
    print("Prune committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
