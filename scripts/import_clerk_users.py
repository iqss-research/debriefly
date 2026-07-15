"""Safely map a Clerk user export to Debriefly local-auth records.

The command is a dry run unless ``--commit`` is supplied. It never rewrites
``user.user_id`` or either ownership foreign key. A normalized CSV is preferred
with these headers:

    clerk_user_id,primary_email,email_verified,email_verified_at

Common Clerk-export aliases are accepted. Password-setup tokens are written
only to an explicitly requested mode-0600 file; raw tokens are never stored in
the database or printed to stdout.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Iterable, Sequence

import dotenv
import reflex as rx
import sqlalchemy as sa
from sqlmodel import Session, select

from debriefly.reflex.backend.models import (
    AuthSession,
    AuthToken,
    Form,
    LocalCredential,
    User,
    UserIdentity,
    UserOpenAISettings,
)


PROVIDER = "clerk"
PASSWORD_SETUP_PURPOSE = "password_setup"
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

ID_HEADERS = ("clerk_user_id", "user_id", "id")
EMAIL_HEADERS = (
    "primary_email",
    "primary_email_address",
    "email_address",
    "email",
)
VERIFIED_HEADERS = (
    "email_verified",
    "primary_email_verified",
    "primary_email_address_verified",
    "verified",
)
VERIFIED_AT_HEADERS = (
    "email_verified_at",
    "primary_email_verified_at",
    "verified_at",
)

TRUE_VALUES = {"1", "true", "yes", "y", "verified"}
FALSE_VALUES = {"", "0", "false", "no", "n", "unverified"}


@dataclass(frozen=True)
class ClerkUserRow:
    line_number: int
    clerk_user_id: str
    email: str | None
    email_normalized: str | None
    email_verified_at: datetime | None

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


@dataclass(frozen=True)
class ImportAction:
    row: ClerkUserRow
    user_id: str
    create_user: bool
    create_identity: bool
    create_credential: bool


@dataclass
class ImportPlan:
    actions: list[ImportAction] = field(default_factory=list)
    skipped_subjects: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    inactive_owner_ids: tuple[str, ...] = ()

    @property
    def can_commit(self) -> bool:
        return not self.conflicts

    @property
    def users_to_create(self) -> int:
        return sum(action.create_user for action in self.actions)

    @property
    def identities_to_create(self) -> int:
        return sum(action.create_identity for action in self.actions)

    @property
    def credentials_to_create(self) -> int:
        return sum(action.create_credential for action in self.actions)

    @property
    def inactive_owner_count(self) -> int:
        return len(self.inactive_owner_ids)


@dataclass(frozen=True)
class SetupToken:
    user_id: str
    email_normalized: str
    raw_token: str
    expires_at: datetime


def normalize_email(value: str) -> str:
    """Use exactly the same normalization as the local login service."""

    normalized = (value or "").strip().casefold()
    if len(normalized) > 320 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("email must be a valid address of at most 320 characters")
    local, domain = normalized.rsplit("@", 1)
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("email domain is invalid") from exc
    normalized = f"{local}@{domain}"
    if len(normalized) > 320:
        raise ValueError("email must be at most 320 characters")
    return normalized


def _token_digest(raw_token: str, secret_key: str) -> str:
    if len(secret_key) < 32:
        raise ValueError(
            "AUTH_SECRET_KEY must be at least 32 characters to issue setup tokens"
        )
    return hmac.new(
        secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _parse_bool(value: str, *, line_number: int) -> bool:
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(
        f"line {line_number}: unsupported email verification value {value!r}"
    )


def _parse_timestamp(value: str, *, line_number: int) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"line {line_number}: invalid ISO email verification timestamp"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _find_header(
    headers: dict[str, str],
    aliases: Sequence[str],
    *,
    label: str,
    required: bool = True,
) -> str | None:
    for alias in aliases:
        if alias in headers:
            return headers[alias]
    if required:
        raise ValueError(
            f"CSV is missing {label}; accepted headers: {', '.join(aliases)}"
        )
    return None


def read_clerk_csv(path: Path, *, now: datetime | None = None) -> list[ClerkUserRow]:
    """Read and validate a Clerk CSV before any database work begins."""

    verification_time = now or datetime.now(timezone.utc)
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        headers = {
            header.strip().casefold(): header
            for header in reader.fieldnames
            if header is not None
        }
        id_header = _find_header(headers, ID_HEADERS, label="Clerk user ID")
        email_header = _find_header(headers, EMAIL_HEADERS, label="primary email")
        verified_header = _find_header(
            headers,
            VERIFIED_HEADERS,
            label="email verification status",
        )
        verified_at_header = _find_header(
            headers,
            VERIFIED_AT_HEADERS,
            label="email verification timestamp",
            required=False,
        )

        rows: list[ClerkUserRow] = []
        seen_subjects: dict[str, int] = {}
        seen_verified_emails: dict[str, int] = {}
        for line_number, raw_row in enumerate(reader, start=2):
            clerk_user_id = (raw_row.get(id_header) or "").strip()
            if not clerk_user_id:
                raise ValueError(f"line {line_number}: Clerk user ID is empty")
            if len(clerk_user_id) > 255:
                raise ValueError(f"line {line_number}: Clerk user ID is too long")
            if clerk_user_id in seen_subjects:
                raise ValueError(
                    f"line {line_number}: duplicate Clerk user ID also found on "
                    f"line {seen_subjects[clerk_user_id]}"
                )
            seen_subjects[clerk_user_id] = line_number

            email = (raw_row.get(email_header) or "").strip() or None
            email_normalized = None
            if email is not None:
                try:
                    email_normalized = normalize_email(email)
                except ValueError as exc:
                    raise ValueError(f"line {line_number}: {exc}") from exc

            verified = _parse_bool(
                raw_row.get(verified_header) or "",
                line_number=line_number,
            )
            if verified and email_normalized is None:
                raise ValueError(
                    f"line {line_number}: verified user has no primary email"
                )

            verified_at = None
            if verified:
                verified_at = (
                    _parse_timestamp(
                        raw_row.get(verified_at_header) or ""
                        if verified_at_header
                        else "",
                        line_number=line_number,
                    )
                    or verification_time
                )
                prior_line = seen_verified_emails.get(email_normalized)
                if prior_line is not None:
                    raise ValueError(
                        f"line {line_number}: verified email duplicates line "
                        f"{prior_line}"
                    )
                assert email_normalized is not None
                seen_verified_emails[email_normalized] = line_number

            rows.append(
                ClerkUserRow(
                    line_number=line_number,
                    clerk_user_id=clerk_user_id,
                    email=email,
                    email_normalized=email_normalized,
                    email_verified_at=verified_at,
                )
            )

    if not rows:
        raise ValueError("CSV has no user rows")
    return rows


def read_inactive_owner_ids(path: Path) -> tuple[str, ...]:
    """Read an exact, private allowlist of owners intentionally left inactive."""

    owner_ids: list[str] = []
    first_lines: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as owner_file:
        for line_number, raw_line in enumerate(owner_file, start=1):
            owner_id = raw_line.rstrip("\r\n")
            if not owner_id:
                raise ValueError(f"line {line_number}: inactive owner ID is empty")
            if owner_id != owner_id.strip() or any(
                character.isspace() for character in owner_id
            ):
                raise ValueError(
                    f"line {line_number}: inactive owner ID contains whitespace"
                )
            if len(owner_id) > 255:
                raise ValueError(f"line {line_number}: inactive owner ID is too long")
            prior_line = first_lines.get(owner_id)
            if prior_line is not None:
                raise ValueError(
                    f"line {line_number}: duplicate inactive owner ID also found "
                    f"on line {prior_line}"
                )
            first_lines[owner_id] = line_number
            owner_ids.append(owner_id)

    if not owner_ids:
        raise ValueError("inactive owner file has no user IDs")
    return tuple(owner_ids)


def _owned_user_ids(session: Session) -> tuple[set[str], set[str], set[str]]:
    form_owner_ids = set(session.exec(select(Form.user_id)).all())
    settings_owner_ids = set(session.exec(select(UserOpenAISettings.user_id)).all())
    return form_owner_ids | settings_owner_ids, form_owner_ids, settings_owner_ids


def build_import_plan(
    session: Session,
    rows: Iterable[ClerkUserRow],
    *,
    issuer: str,
    create_missing_users: bool = False,
    inactive_owner_ids: Sequence[str] = (),
) -> ImportPlan:
    """Build a complete plan and reject ambiguous or orphaned ownership."""

    plan = ImportPlan()
    issuer = issuer.strip()
    if not issuer or len(issuer) > 255:
        plan.conflicts.append("issuer must be non-empty and at most 255 characters")
        return plan

    users = {user.user_id: user for user in session.exec(select(User)).all()}
    identities = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == PROVIDER,
            UserIdentity.issuer == issuer,
        )
    ).all()
    identity_by_subject = {identity.subject: identity for identity in identities}
    identity_by_user = {identity.user_id: identity for identity in identities}
    credential_user_ids = {
        credential.user_id for credential in session.exec(select(LocalCredential)).all()
    }

    owners, form_owner_ids, settings_owner_ids = _owned_user_ids(session)
    missing_form_users = sorted(form_owner_ids - users.keys())
    missing_settings_users = sorted(settings_owner_ids - users.keys())
    if missing_form_users:
        plan.conflicts.append(
            "forms reference missing users: " + ", ".join(missing_form_users)
        )
    if missing_settings_users:
        plan.conflicts.append(
            "OpenAI settings reference missing users: "
            + ", ".join(missing_settings_users)
        )

    email_owner: dict[str, str] = {}
    for user in users.values():
        if not user.email_normalized:
            continue
        existing_owner = email_owner.get(user.email_normalized)
        if existing_owner is not None and existing_owner != user.user_id:
            plan.conflicts.append(
                f"database email {user.email_normalized!r} belongs to multiple users"
            )
        email_owner[user.email_normalized] = user.user_id

    planned_user_subject: dict[str, str] = {}
    planned_credential_users = set(credential_user_ids)
    for row in rows:
        identity = identity_by_subject.get(row.clerk_user_id)
        direct_user = users.get(row.clerk_user_id)
        if (
            identity is not None
            and direct_user is not None
            and identity.user_id != direct_user.user_id
        ):
            plan.conflicts.append(
                f"line {row.line_number}: identity maps to {identity.user_id!r}, "
                f"but subject is also an existing user ID"
            )
            continue

        if identity is not None:
            user_id = identity.user_id
            if user_id not in users:
                plan.conflicts.append(
                    f"line {row.line_number}: identity references missing user {user_id!r}"
                )
                continue
            create_user = False
        elif direct_user is not None:
            user_id = direct_user.user_id
            create_user = False
        elif create_missing_users:
            user_id = row.clerk_user_id
            create_user = True
        else:
            plan.skipped_subjects.append(row.clerk_user_id)
            continue

        prior_subject = planned_user_subject.get(user_id)
        existing_for_user = identity_by_user.get(user_id)
        if prior_subject is not None and prior_subject != row.clerk_user_id:
            plan.conflicts.append(
                f"line {row.line_number}: multiple subjects map to user {user_id!r}"
            )
            continue
        if (
            existing_for_user is not None
            and existing_for_user.subject != row.clerk_user_id
        ):
            plan.conflicts.append(
                f"line {row.line_number}: user {user_id!r} already has a different "
                "identity for this issuer"
            )
            continue
        planned_user_subject[user_id] = row.clerk_user_id

        if identity is not None:
            if (
                identity.email_normalized
                and row.email_normalized
                and identity.email_normalized != row.email_normalized
            ):
                plan.conflicts.append(
                    f"line {row.line_number}: imported email conflicts with existing "
                    "identity metadata"
                )
                continue

        target_user = users.get(user_id)
        if row.email_verified:
            assert row.email_normalized is not None
            owner = email_owner.get(row.email_normalized)
            if owner is not None and owner != user_id:
                plan.conflicts.append(
                    f"line {row.line_number}: verified email already belongs to "
                    f"another user {owner!r}"
                )
                continue
            if (
                target_user is not None
                and target_user.email_normalized
                and target_user.email_normalized != row.email_normalized
            ):
                plan.conflicts.append(
                    f"line {row.line_number}: verified email conflicts with user "
                    f"{user_id!r}"
                )
                continue
            email_owner[row.email_normalized] = user_id
            planned_credential_users.add(user_id)
        elif user_id in owners and user_id not in credential_user_ids:
            plan.conflicts.append(
                f"line {row.line_number}: owner {user_id!r} lacks a verified email"
            )
            continue

        plan.actions.append(
            ImportAction(
                row=row,
                user_id=user_id,
                create_user=create_user,
                create_identity=identity is None,
                create_credential=(
                    row.email_verified and user_id not in credential_user_ids
                ),
            )
        )

    uncovered_owners = {
        owner
        for owner in owners
        if owner in users and owner not in planned_credential_users
    }
    requested_inactive_owner_ids = tuple(inactive_owner_ids)
    inactive_owner_id_set = set(requested_inactive_owner_ids)
    duplicate_inactive_owner_count = len(requested_inactive_owner_ids) - len(
        inactive_owner_id_set
    )
    if duplicate_inactive_owner_count:
        plan.conflicts.append(
            "inactive-owner allowlist contains "
            f"{duplicate_inactive_owner_count} duplicate ID(s)"
        )

    unknown_inactive_owners = inactive_owner_id_set - users.keys()
    if unknown_inactive_owners:
        plan.conflicts.append(
            "inactive-owner allowlist contains "
            f"{len(unknown_inactive_owners)} unknown user ID(s)"
        )
    non_owner_inactive_users = (inactive_owner_id_set & users.keys()) - owners
    if non_owner_inactive_users:
        plan.conflicts.append(
            "inactive-owner allowlist contains "
            f"{len(non_owner_inactive_users)} user ID(s) that own no forms or settings"
        )
    covered_inactive_owners = (inactive_owner_id_set & owners) - uncovered_owners
    if covered_inactive_owners:
        plan.conflicts.append(
            "inactive-owner allowlist contains "
            f"{len(covered_inactive_owners)} owner ID(s) that already have or will "
            "receive local credentials"
        )

    identity_user_ids = set(session.exec(select(UserIdentity.user_id)).all())
    token_user_ids = set(session.exec(select(AuthToken.user_id)).all())
    session_user_ids = set(session.exec(select(AuthSession.user_id)).all())
    auth_artifact_inactive_owners = inactive_owner_id_set & (
        identity_user_ids | token_user_ids | session_user_ids
    )
    if auth_artifact_inactive_owners:
        plan.conflicts.append(
            "inactive-owner allowlist contains "
            f"{len(auth_artifact_inactive_owners)} owner ID(s) with existing local "
            "authentication artifacts"
        )

    unapproved_uncovered_owners = sorted(uncovered_owners - inactive_owner_id_set)
    if unapproved_uncovered_owners:
        plan.conflicts.append(
            "owners without a verified local credential import: "
            + ", ".join(unapproved_uncovered_owners)
        )
    if inactive_owner_id_set == uncovered_owners and not plan.conflicts:
        plan.inactive_owner_ids = tuple(sorted(inactive_owner_id_set))
    return plan


def _active_setup_token_user_ids(
    session: Session,
    *,
    now: datetime,
) -> set[str]:
    return set(
        session.exec(
            select(AuthToken.user_id).where(
                AuthToken.purpose == PASSWORD_SETUP_PURPOSE,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > now,
            )
        ).all()
    )


def users_requiring_setup_tokens(
    session: Session,
    plan: ImportPlan,
    *,
    now: datetime,
) -> set[str]:
    """Return imported users that have neither a password nor an active token."""

    credentials = {
        credential.user_id: credential
        for credential in session.exec(select(LocalCredential)).all()
    }
    active_tokens = _active_setup_token_user_ids(session, now=now)
    required: set[str] = set()
    for action in plan.actions:
        if not action.row.email_verified:
            continue
        credential = credentials.get(action.user_id)
        if credential is not None and credential.password_hash:
            continue
        if action.user_id not in active_tokens:
            required.add(action.user_id)
    return required


def apply_import_plan(
    session: Session,
    plan: ImportPlan,
    *,
    issuer: str,
    setup_user_ids: set[str],
    setup_token_hours: int,
    token_secret: str,
    now: datetime,
) -> list[SetupToken]:
    """Apply a previously validated plan in the caller's transaction."""

    if not plan.can_commit:
        raise ValueError("refusing to apply an import plan with conflicts")

    setup_tokens: list[SetupToken] = []
    for inactive_owner_id in plan.inactive_owner_ids:
        inactive_owner = session.get(User, inactive_owner_id)
        if inactive_owner is None:
            raise ValueError("inactive owner disappeared after plan validation")
        has_auth_artifact = (
            session.get(LocalCredential, inactive_owner_id) is not None
            or session.exec(
                select(UserIdentity.id).where(UserIdentity.user_id == inactive_owner_id)
            ).first()
            is not None
            or session.exec(
                select(AuthToken.id).where(AuthToken.user_id == inactive_owner_id)
            ).first()
            is not None
            or session.exec(
                select(AuthSession.id).where(AuthSession.user_id == inactive_owner_id)
            ).first()
            is not None
        )
        if has_auth_artifact:
            raise ValueError(
                "inactive owner gained an authentication artifact after plan "
                "validation"
            )
        if inactive_owner.status != "inactive":
            inactive_owner.status = "inactive"
            inactive_owner.auth_version += 1
            inactive_owner.updated_at = now
            session.add(inactive_owner)

    for action in plan.actions:
        user = session.get(User, action.user_id)
        if user is None:
            user = User(
                user_id=action.user_id,
                status="active" if action.row.email_verified else "pending",
                created_at=now,
                updated_at=now,
            )
            session.add(user)

        if action.row.email_verified:
            user.email_normalized = action.row.email_normalized
            if user.email_verified_at is None:
                user.email_verified_at = action.row.email_verified_at
            user.status = "active"
        user.updated_at = now
        session.add(user)

        identity = session.exec(
            select(UserIdentity).where(
                UserIdentity.provider == PROVIDER,
                UserIdentity.issuer == issuer,
                UserIdentity.subject == action.row.clerk_user_id,
            )
        ).first()
        if identity is None:
            identity = UserIdentity(
                user_id=action.user_id,
                provider=PROVIDER,
                issuer=issuer,
                subject=action.row.clerk_user_id,
                email=action.row.email,
                email_normalized=action.row.email_normalized,
                email_verified_at=action.row.email_verified_at,
                link_source="csv_import",
                created_at=now,
            )
        else:
            if identity.email is None:
                identity.email = action.row.email
            if identity.email_normalized is None:
                identity.email_normalized = action.row.email_normalized
            if identity.email_verified_at is None:
                identity.email_verified_at = action.row.email_verified_at
        session.add(identity)

        credential = session.get(LocalCredential, action.user_id)
        if action.row.email_verified and credential is None:
            credential = LocalCredential(user_id=action.user_id)
            session.add(credential)

        if action.user_id in setup_user_ids:
            assert action.row.email_normalized is not None
            raw_token = secrets.token_urlsafe(32)
            token_digest = _token_digest(raw_token, token_secret)
            expires_at = now + timedelta(hours=setup_token_hours)
            session.add(
                AuthToken(
                    user_id=action.user_id,
                    purpose=PASSWORD_SETUP_PURPOSE,
                    token_digest=token_digest,
                    email_normalized=action.row.email_normalized,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            setup_tokens.append(
                SetupToken(
                    user_id=action.user_id,
                    email_normalized=action.row.email_normalized,
                    raw_token=raw_token,
                    expires_at=expires_at,
                )
            )

    session.flush()
    inactive_owner_id_set = set(plan.inactive_owner_ids)
    current_user_ids = set(session.exec(select(User.user_id)).all())
    current_credential_user_ids = set(
        session.exec(select(LocalCredential.user_id)).all()
    )
    current_owners, _, _ = _owned_user_ids(session)
    if current_owners - current_user_ids:
        raise ValueError("ownership became orphaned during import")
    current_uncovered_owners = {
        owner for owner in current_owners if owner not in current_credential_user_ids
    }
    if current_uncovered_owners != inactive_owner_id_set:
        raise ValueError("inactive owner coverage changed during import")

    current_identity_user_ids = set(session.exec(select(UserIdentity.user_id)).all())
    current_token_user_ids = set(session.exec(select(AuthToken.user_id)).all())
    current_session_user_ids = set(session.exec(select(AuthSession.user_id)).all())
    if inactive_owner_id_set & (
        current_credential_user_ids
        | current_identity_user_ids
        | current_token_user_ids
        | current_session_user_ids
    ):
        raise ValueError("inactive owner received an authentication artifact")
    if any(
        session.get(User, inactive_owner_id).status != "inactive"
        for inactive_owner_id in plan.inactive_owner_ids
    ):
        raise ValueError("inactive owner post-import assertion failed")
    return setup_tokens


def write_setup_tokens(path: Path, tokens: Iterable[SetupToken]) -> None:
    """Write raw setup tokens once to a new owner-readable file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=(
                    "user_id",
                    "email_normalized",
                    "setup_token",
                    "expires_at",
                ),
            )
            writer.writeheader()
            for token in tokens:
                writer.writerow(
                    {
                        "user_id": token.user_id,
                        "email_normalized": token.email_normalized,
                        "setup_token": token.raw_token,
                        "expires_at": token.expires_at.isoformat(),
                    }
                )
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _acquire_import_lock(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('debriefly_clerk_user_import'))"
            )
        )


def _print_plan(plan: ImportPlan, *, row_count: int) -> None:
    print(f"CSV rows: {row_count}")
    print(f"Mapped rows: {len(plan.actions)}")
    print(f"Skipped Clerk-only rows: {len(plan.skipped_subjects)}")
    print(f"Users to create: {plan.users_to_create}")
    print(f"Identities to create: {plan.identities_to_create}")
    print(f"Credentials to create: {plan.credentials_to_create}")
    print(
        "Intentionally inactive owners without credentials: "
        f"{plan.inactive_owner_count}"
    )
    if plan.conflicts:
        print("Conflicts:", file=sys.stderr)
        for conflict in plan.conflicts:
            print(f"  - {conflict}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Clerk export or normalized CSV")
    parser.add_argument(
        "--issuer",
        required=True,
        help="Exact Clerk JWT issuer for this export",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply the validated plan (default is dry-run)",
    )
    parser.add_argument(
        "--create-missing-users",
        action="store_true",
        help="Also create users that never signed in to Debriefly",
    )
    parser.add_argument(
        "--inactive-owner-file",
        type=Path,
        help=(
            "Private file containing the exact existing Debriefly owner IDs absent "
            "from the Clerk export that will be marked inactive without local "
            "credentials, one ID per line"
        ),
    )
    setup_group = parser.add_mutually_exclusive_group()
    setup_group.add_argument(
        "--setup-token-output",
        type=Path,
        help="New mode-0600 CSV that receives one-time raw setup tokens",
    )
    setup_group.add_argument(
        "--skip-setup-tokens",
        action="store_true",
        help="Import credentials without issuing password-setup tokens",
    )
    parser.add_argument(
        "--setup-token-hours",
        type=int,
        default=48,
        help="Setup-token lifetime (default: 48 hours)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.setup_token_hours < 1 or args.setup_token_hours > 168:
        print("setup-token-hours must be between 1 and 168", file=sys.stderr)
        return 2

    try:
        rows = read_clerk_csv(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"CSV validation failed: {exc}", file=sys.stderr)
        return 2

    inactive_owner_ids: tuple[str, ...] = ()
    if args.inactive_owner_file is not None:
        try:
            inactive_owner_ids = read_inactive_owner_ids(args.inactive_owner_file)
        except (OSError, ValueError) as exc:
            print(f"Inactive owner file validation failed: {exc}", file=sys.stderr)
            return 2

    dotenv.load_dotenv()
    now = datetime.now(timezone.utc)
    setup_output_written = False
    with rx.session() as session:
        try:
            _acquire_import_lock(session)
            plan = build_import_plan(
                session,
                rows,
                issuer=args.issuer,
                create_missing_users=args.create_missing_users,
                inactive_owner_ids=inactive_owner_ids,
            )
            _print_plan(plan, row_count=len(rows))
            if not plan.can_commit:
                session.rollback()
                return 2

            setup_user_ids = users_requiring_setup_tokens(
                session,
                plan,
                now=now,
            )
            print(f"Users requiring a setup token: {len(setup_user_ids)}")
            if not args.commit:
                session.rollback()
                print("Dry run complete; no database changes were made.")
                return 0

            if (
                setup_user_ids
                and args.setup_token_output is None
                and not args.skip_setup_tokens
            ):
                print(
                    "Refusing to commit: pass --setup-token-output or "
                    "--skip-setup-tokens explicitly.",
                    file=sys.stderr,
                )
                session.rollback()
                return 2

            issued_user_ids = set() if args.skip_setup_tokens else setup_user_ids
            token_secret = os.getenv("AUTH_SECRET_KEY", "")
            if issued_user_ids and len(token_secret) < 32:
                print(
                    "Refusing to issue setup tokens: AUTH_SECRET_KEY must be at "
                    "least 32 characters.",
                    file=sys.stderr,
                )
                session.rollback()
                return 2
            setup_tokens = apply_import_plan(
                session,
                plan,
                issuer=args.issuer.strip(),
                setup_user_ids=issued_user_ids,
                setup_token_hours=args.setup_token_hours,
                token_secret=token_secret,
                now=now,
            )
            if args.setup_token_output is not None:
                write_setup_tokens(args.setup_token_output, setup_tokens)
                setup_output_written = True
            session.commit()
        except BaseException as exc:
            session.rollback()
            if setup_output_written and args.setup_token_output is not None:
                args.setup_token_output.unlink(missing_ok=True)
            print(f"Import failed and was rolled back: {exc}", file=sys.stderr)
            return 1

    print(f"Import committed. Setup tokens issued: {len(setup_tokens)}")
    if args.setup_token_output is not None:
        print(
            f"Sensitive setup tokens were written to {args.setup_token_output} "
            "with mode 0600. Deliver and delete this file securely."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
