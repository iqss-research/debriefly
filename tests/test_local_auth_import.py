from datetime import datetime, timedelta, timezone
import hashlib
import hmac

import pytest

from debriefly.reflex.backend.models import (
    AuthSession,
    AuthToken,
    Form,
    LocalCredential,
    User,
    UserIdentity,
    UserOpenAISettings,
)
from debriefly.reflex.local_auth import request_password_email
from sqlmodel import Session, SQLModel, create_engine, select
from scripts.import_clerk_users import (
    ClerkUserRow,
    apply_import_plan,
    build_import_plan,
    read_clerk_csv,
    read_inactive_owner_ids,
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


def test_exact_inactive_owner_allowlist_preserves_owned_data(tmp_path):
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc)
    active_row = _verified_row("user_active")
    inactive_owner_id = "user_intentionally_inactive"

    with Session(engine) as session:
        session.add(User(user_id=active_row.clerk_user_id))
        session.add(
            User(
                user_id=inactive_owner_id,
                email_normalized="inactive@example.com",
                email_verified_at=now,
                role="admin",
            )
        )
        session.add(
            Form(
                id=201,
                name="Active survey",
                code="active-survey",
                user_id=active_row.clerk_user_id,
            )
        )
        session.add(
            Form(
                id=202,
                name="Preserved inactive survey",
                code="inactive-survey",
                user_id=inactive_owner_id,
            )
        )
        session.commit()
        original_inactive_email_verified_at = session.get(
            User, inactive_owner_id
        ).email_verified_at

        plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id,),
        )

        assert plan.can_commit
        assert plan.inactive_owner_count == 1
        assert [action.user_id for action in plan.actions] == [active_row.clerk_user_id]

        apply_import_plan(
            session,
            plan,
            issuer="https://clerk.example.test",
            setup_user_ids=set(),
            setup_token_hours=48,
            token_secret="",
            now=now,
        )
        session.commit()

        assert session.get(Form, 201).user_id == active_row.clerk_user_id
        assert session.get(Form, 202).user_id == inactive_owner_id
        inactive_owner = session.get(User, inactive_owner_id)
        assert inactive_owner is not None
        assert inactive_owner.status == "inactive"
        assert inactive_owner.auth_version == 2
        assert inactive_owner.role == "admin"
        assert inactive_owner.email_normalized == "inactive@example.com"
        assert inactive_owner.email_verified_at == original_inactive_email_verified_at
        assert (
            session.exec(
                select(UserIdentity).where(UserIdentity.user_id == inactive_owner_id)
            ).first()
            is None
        )
        assert session.get(LocalCredential, inactive_owner_id) is None
        assert request_password_email(session, "inactive@example.com") is None
        assert (
            session.exec(
                select(AuthToken).where(AuthToken.user_id == inactive_owner_id)
            ).first()
            is None
        )

        second_plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id,),
        )
        assert second_plan.can_commit
        apply_import_plan(
            session,
            second_plan,
            issuer="https://clerk.example.test",
            setup_user_ids=set(),
            setup_token_hours=48,
            token_secret="",
            now=now,
        )
        session.commit()
        assert session.get(User, inactive_owner_id).auth_version == 2


def test_inactive_owner_allowlist_must_exactly_match_uncovered_owners(tmp_path):
    engine = _engine(tmp_path)
    active_row = _verified_row("user_active")
    inactive_owner_id = "user_intentionally_inactive"

    with Session(engine) as session:
        session.add(User(user_id=active_row.clerk_user_id))
        session.add(User(user_id=inactive_owner_id))
        session.add(
            Form(
                name="Active owner survey",
                code="active-owner-survey",
                user_id=active_row.clerk_user_id,
            )
        )
        session.add(
            Form(
                name="Preserved inactive survey",
                code="inactive-survey",
                user_id=inactive_owner_id,
            )
        )
        session.commit()

        missing_plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
        )
        extra_plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id, active_row.clerk_user_id),
        )
        duplicate_plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id, inactive_owner_id),
        )

    assert not missing_plan.can_commit
    assert any(
        "owners without a verified local credential import" in error
        for error in missing_plan.conflicts
    )
    assert not extra_plan.can_commit
    assert any(
        "1 owner ID(s) that already have or will receive local credentials" in error
        for error in extra_plan.conflicts
    )
    assert not duplicate_plan.can_commit
    assert any("1 duplicate ID(s)" in error for error in duplicate_plan.conflicts)


def test_inactive_owner_allowlist_rejects_unknown_and_non_owner_ids(tmp_path):
    engine = _engine(tmp_path)
    active_row = _verified_row("user_active")
    inactive_owner_id = "user_intentionally_inactive"
    non_owner_id = "user_without_owned_data"

    with Session(engine) as session:
        session.add(User(user_id=active_row.clerk_user_id))
        session.add(User(user_id=inactive_owner_id))
        session.add(User(user_id=non_owner_id))
        session.add(
            Form(
                name="Preserved inactive survey",
                code="inactive-survey",
                user_id=inactive_owner_id,
            )
        )
        session.commit()

        plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(
                inactive_owner_id,
                non_owner_id,
                "user_unknown",
            ),
        )

    assert not plan.can_commit
    assert any("1 unknown user ID(s)" in error for error in plan.conflicts)
    assert any(
        "1 user ID(s) that own no forms or settings" in error
        for error in plan.conflicts
    )


def test_inactive_owner_allowlist_covers_settings_only_owner(tmp_path):
    engine = _engine(tmp_path)
    active_row = _verified_row("user_active")
    inactive_owner_id = "user_settings_only_owner"

    with Session(engine) as session:
        session.add(User(user_id=active_row.clerk_user_id))
        session.add(User(user_id=inactive_owner_id))
        session.add(
            UserOpenAISettings(
                user_id=inactive_owner_id,
                api_key="preserved-key",
                model="gpt-4o-mini",
            )
        )
        session.commit()

        plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id,),
        )

    assert plan.can_commit
    assert plan.inactive_owner_ids == (inactive_owner_id,)


def test_inactive_owner_file_is_private_and_fail_closed(tmp_path):
    owner_file = tmp_path / "inactive-owners.txt"
    owner_file.write_text(
        "user_one\nuser_two\n",
        encoding="utf-8",
    )
    assert read_inactive_owner_ids(owner_file) == ("user_one", "user_two")

    owner_file.write_text(
        "user_private_value\nuser_private_value\n",
        encoding="utf-8",
    )
    try:
        read_inactive_owner_ids(owner_file)
    except ValueError as exc:
        assert "duplicate inactive owner ID" in str(exc)
        assert "user_private_value" not in str(exc)
    else:
        raise AssertionError("duplicate inactive owner IDs should be rejected")

    owner_file.write_text("\n", encoding="utf-8")
    try:
        read_inactive_owner_ids(owner_file)
    except ValueError as exc:
        assert "inactive owner ID is empty" in str(exc)
    else:
        raise AssertionError("blank inactive owner IDs should be rejected")

    owner_file.write_text(" user_private_value\n", encoding="utf-8")
    try:
        read_inactive_owner_ids(owner_file)
    except ValueError as exc:
        assert "inactive owner ID contains whitespace" in str(exc)
        assert "user_private_value" not in str(exc)
    else:
        raise AssertionError("whitespace-padded inactive owner IDs should be rejected")


def test_inactive_owner_allowlist_cannot_waive_unverified_matched_owner(tmp_path):
    engine = _engine(tmp_path)
    owner_id = "user_unverified_owner"
    unverified_row = ClerkUserRow(
        line_number=2,
        clerk_user_id=owner_id,
        email="owner@example.com",
        email_normalized="owner@example.com",
        email_verified_at=None,
    )

    with Session(engine) as session:
        session.add(User(user_id=owner_id))
        session.add(
            Form(
                name="Unverified owner survey",
                code="unverified-owner-survey",
                user_id=owner_id,
            )
        )
        session.commit()

        plan = build_import_plan(
            session,
            [unverified_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(owner_id,),
        )

    assert not plan.can_commit
    assert plan.inactive_owner_count == 0
    assert any("lacks a verified email" in error for error in plan.conflicts)


@pytest.mark.parametrize(
    ("artifact", "expected_conflict"),
    (
        ("credential", "already have or will receive local credentials"),
        ("identity", "with existing local authentication artifacts"),
        ("token", "with existing local authentication artifacts"),
        ("session", "with existing local authentication artifacts"),
    ),
)
def test_inactive_owner_allowlist_rejects_existing_auth_artifacts(
    tmp_path,
    artifact,
    expected_conflict,
):
    engine = _engine(tmp_path)
    now = datetime.now(timezone.utc)
    active_row = _verified_row("user_active")
    inactive_owner_id = "user_inactive_with_auth_artifact"

    with Session(engine) as session:
        session.add(User(user_id=active_row.clerk_user_id))
        session.add(User(user_id=inactive_owner_id))
        session.add(
            Form(
                name="Inactive owner survey",
                code="inactive-owner-survey",
                user_id=inactive_owner_id,
            )
        )
        if artifact == "credential":
            session.add(LocalCredential(user_id=inactive_owner_id))
        elif artifact == "identity":
            session.add(
                UserIdentity(
                    user_id=inactive_owner_id,
                    provider="clerk",
                    issuer="https://clerk.example.test",
                    subject="deleted_subject",
                )
            )
        elif artifact == "token":
            session.add(
                AuthToken(
                    user_id=inactive_owner_id,
                    purpose="password_setup",
                    token_digest="existing-token-digest",
                    expires_at=now + timedelta(hours=1),
                )
            )
        else:
            session.add(
                AuthSession(
                    user_id=inactive_owner_id,
                    token_digest="existing-session-digest",
                    auth_version=1,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
        session.commit()

        plan = build_import_plan(
            session,
            [active_row],
            issuer="https://clerk.example.test",
            inactive_owner_ids=(inactive_owner_id,),
        )

    assert not plan.can_commit
    assert any(expected_conflict in error for error in plan.conflicts)


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
