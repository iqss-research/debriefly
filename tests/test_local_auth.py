from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import reflex as rx
from reflex.event import Event, get_hydrate_event

import debriefly.reflex.auth_api as auth_api
import debriefly.reflex.auth_middleware as auth_middleware
import debriefly.reflex.local_auth as local_auth
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import (
    AuthSession,
    AuthToken,
    LocalCredential,
    User,
)
from debriefly.reflex.pages.signin import _TOKEN_PAGE_META
from sqlmodel import Session, SQLModel, create_engine, select


def _configure(monkeypatch, *, production: bool = False):
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-0123456789abcdef")
    monkeypatch.setenv(
        "AUTH_PUBLIC_URL",
        "https://debriefly.example" if production else "http://localhost:3000",
    )
    monkeypatch.setenv(
        "AUTH_ALLOWED_ORIGINS",
        "https://debriefly.example" if production else "http://localhost:3000",
    )
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true" if production else "false")
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_API_PUBLIC_URL", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setenv("AUTH_ALLOW_REGISTRATION", "true")
    local_auth.get_auth_settings.cache_clear()
    with auth_api._attempts_lock:
        auth_api._attempts.clear()


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def _token_from_email(body: str) -> str:
    url = next(line for line in body.splitlines() if "token=" in line)
    return parse_qs(urlparse(url).query)["token"][0]


def test_token_pages_preserve_origin_without_leaking_the_token_url():
    # `no-referrer` turns Origin into `null` for the native dev POST from
    # frontend :3000 to backend :8000, causing the CSRF check to reject it.
    assert _TOKEN_PAGE_META == [{"name": "referrer", "content": "strict-origin"}]


def test_email_token_holder_replaces_any_legacy_pending_password(monkeypatch, tmp_path):
    _configure(monkeypatch)
    assert (
        local_auth.auth_api_endpoint("forgot-password")
        == "http://localhost:8000/_event/auth/forgot-password"
    )
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_auth.rx, "session", lambda: Session(engine))

    with Session(engine) as session:
        pending = local_auth.register_local_user(session, "Person@Example.ORG")
        session.commit()
        assert pending is not None
        user = session.exec(select(User)).one()
        assert session.get(LocalCredential, user.user_id) is None
        assert user.email_verified_at is None
        assert user.status == "pending"

        verify_token = _token_from_email(pending.body)
        with pytest.raises(local_auth.InvalidPassword):
            local_auth.verify_email(
                session,
                verify_token,
                "too short",
                "too short",
            )
        with pytest.raises(local_auth.InvalidPassword):
            local_auth.verify_email(
                session,
                verify_token,
                "legitimate safe password",
                "different safe password",
            )
        stored_token = session.exec(select(AuthToken)).one()
        assert stored_token.used_at is None

        # Simulate a pending account created by the vulnerable pre-email-first
        # implementation. The email-token holder must replace this hash.
        session.add(
            LocalCredential(
                user_id=user.user_id,
                password_hash=local_auth.hash_password("attacker chosen password"),
            )
        )
        session.commit()
        assert local_auth.verify_email(
            session,
            verify_token,
            "legitimate safe password",
            "legitimate safe password",
        )
        session.commit()
        assert not local_auth.verify_email(
            session,
            verify_token,
            "another legitimate password",
            "another legitimate password",
        )
        assert (
            local_auth.authenticate_password(
                session, "person@example.org", "attacker chosen password"
            )
            is None
        )

        result = local_auth.authenticate_password(
            session, "person@example.org", "legitimate safe password"
        )
        assert result is not None
        _, raw_session = result
        session.commit()

    cookie_name = local_auth.get_auth_settings().cookie_name
    resolved = local_auth.resolve_cookie_session(
        f"{cookie_name}={raw_session}", origin="http://localhost:3000"
    )
    assert resolved is not None

    with Session(engine) as session:
        reset_email = local_auth.request_password_email(session, "person@example.org")
        session.commit()
        assert reset_email is not None
        reset_token = _token_from_email(reset_email.body)
        assert local_auth.reset_password(
            session,
            reset_token,
            "a different final password",
            "a different final password",
        )
        session.commit()
        assert not local_auth.reset_password(
            session,
            reset_token,
            "a different final password",
            "a different final password",
        )
        stored_session = session.exec(select(AuthSession)).one()
        assert stored_session.revoked_at is not None

    assert (
        local_auth.resolve_cookie_session(
            f"{cookie_name}={raw_session}", origin="http://localhost:3000"
        )
        is None
    )


def test_migrated_verified_user_can_set_up_a_password(monkeypatch, tmp_path):
    _configure(monkeypatch)
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_auth.rx, "session", lambda: Session(engine))
    now = local_auth._now()

    with Session(engine) as session:
        user = User(
            user_id="user_migrated",
            email_normalized="migrated@example.org",
            email_verified_at=now,
            status="active",
            role="user",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.add(LocalCredential(user_id=user.user_id))
        session.commit()

        # Registration stays non-enumerating and does not alter a verified user.
        assert local_auth.register_local_user(session, "migrated@example.org") is None
        assert session.exec(select(AuthToken)).first() is None

        setup_email = local_auth.request_password_email(session, "migrated@example.org")
        session.commit()
        assert setup_email is not None
        assert setup_email.purpose == local_auth.PASSWORD_SETUP
        setup_token = _token_from_email(setup_email.body)
        assert local_auth.reset_password(
            session,
            setup_token,
            "migrated account password",
            "migrated account password",
        )
        session.commit()
        assert (
            local_auth.authenticate_password(
                session,
                "migrated@example.org",
                "migrated account password",
            )
            is not None
        )


def test_login_http_endpoint_sets_production_cookie_and_checks_origin(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, production=True)
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_auth.rx, "session", lambda: Session(engine))
    monkeypatch.setattr(auth_api.rx, "session", lambda: Session(engine))

    api = FastAPI()
    auth_api.register_auth_routes(api)
    client = TestClient(api, base_url="https://debriefly.example")

    # Link-preview and email-scanner GETs must never mutate verification state.
    scanner = client.get("/_event/auth/verify?token=anything", follow_redirects=False)
    assert scanner.status_code == 405

    no_email = client.post(
        "/_event/auth/forgot-password",
        data={"email": "person@example.org"},
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert no_email.status_code == 303
    assert no_email.headers["location"].endswith(
        "/forgot-password?error=email-not-configured"
    )

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "Debriefly <accounts@debriefly.example>")
    sent = []

    def capture_email(message):
        sent.append(message)
        return True

    monkeypatch.setattr(auth_api, "send_auth_email", capture_email)

    blocked_registration = client.post(
        "/_event/auth/register",
        data={"email": "person@example.org"},
        headers={"Origin": "https://attacker.example"},
        follow_redirects=False,
    )
    assert blocked_registration.status_code == 403

    registration = client.post(
        "/_event/auth/register",
        data={
            "email": "person@example.org",
            # A stale 0.9.3 form may still submit these fields. They must never
            # become an active credential before email ownership is proven.
            "password": "attacker chosen password",
            "password_confirm": "attacker chosen password",
        },
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert registration.status_code == 303
    assert registration.headers["location"].endswith("/signin?notice=check-email")
    assert len(sent) == 1
    verify_token = _token_from_email(sent[0].body)
    with Session(engine) as session:
        user = session.exec(select(User)).one()
        assert user.status == "pending"
        assert session.get(LocalCredential, user.user_id) is None

    invalid_password = client.post(
        "/_event/auth/verify",
        data={
            "token": verify_token,
            "password": "legitimate safe password",
            "password_confirm": "different safe password",
        },
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert invalid_password.status_code == 303
    invalid_location = urlparse(invalid_password.headers["location"])
    invalid_query = parse_qs(invalid_location.query)
    assert invalid_location.path == "/verify-email"
    assert invalid_query["token"] == [verify_token]
    assert invalid_query["error"] == ["invalid-password"]
    with Session(engine) as session:
        assert session.exec(select(AuthToken)).one().used_at is None
        assert session.exec(select(User)).one().status == "pending"

    verification = client.post(
        "/_event/auth/verify",
        data={
            "token": verify_token,
            "password": "legitimate safe password",
            "password_confirm": "legitimate safe password",
        },
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert verification.status_code == 303
    assert verification.headers["location"].endswith("/signin?notice=verified")

    attacker_login = client.post(
        "/_event/auth/login",
        data={"email": "person@example.org", "password": "attacker chosen password"},
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert attacker_login.status_code == 303
    assert attacker_login.headers["location"].endswith("/signin?error=invalid")

    blocked = client.post(
        "/_event/auth/login",
        data={"email": "person@example.org", "password": "correct horse battery"},
        headers={"Origin": "https://attacker.example"},
        follow_redirects=False,
    )
    assert blocked.status_code == 403

    response = client.post(
        "/_event/auth/login",
        data={
            "email": "person@example.org",
            "password": "legitimate safe password",
            "next": "/user",
        },
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://debriefly.example/user"
    cookie = response.headers["set-cookie"]
    assert "__Host-debriefly_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie

    logout = client.post(
        "/_event/auth/logout",
        headers={"Origin": "https://debriefly.example"},
        follow_redirects=False,
    )
    assert logout.status_code == 303
    assert "Max-Age=0" in logout.headers["set-cookie"]
    with Session(engine) as session:
        assert session.exec(select(AuthSession)).one().revoked_at is not None

    local_auth.get_auth_settings.cache_clear()


def test_hydration_clears_researcher_state_before_serialization(monkeypatch):
    root = rx.State(_reflex_internal_init=True)

    async def exercise():
        main = await root.get_state(MainState)
        main._user_id = "previous-user"
        main.is_authenticated = True
        main.config = {"private": "previous-user-value"}
        monkeypatch.setattr(
            auth_middleware,
            "resolve_cookie_session",
            lambda *args, **kwargs: None,
        )
        event = Event(
            token="client-token",
            name=get_hydrate_event(root),
            router_data={},
        )
        update = await auth_middleware.LocalAuthMiddleware().preprocess(
            None, root, event
        )
        assert update is None  # public hydration continues after sanitization
        assert main.user_id == ""
        assert main.config == {}
        assert not main.is_authenticated
        assert main.auth_checked

    asyncio.run(exercise())
