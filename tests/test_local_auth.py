from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
import reflex as rx
from reflex.event import Event, get_hydrate_event

import debriefly.reflex.auth_api as auth_api
import debriefly.reflex.auth_middleware as auth_middleware
import debriefly.reflex.local_auth as local_auth
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import AuthSession, LocalCredential, User
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
    local_auth.get_auth_settings.cache_clear()


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


def test_migrated_style_password_setup_revokes_sessions(monkeypatch, tmp_path):
    _configure(monkeypatch)
    assert (
        local_auth.auth_api_endpoint("forgot-password")
        == "http://localhost:8000/_event/auth/forgot-password"
    )
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_auth.rx, "session", lambda: Session(engine))

    with Session(engine) as session:
        pending = local_auth.register_local_user(
            session, "Person@Example.ORG", "correct horse battery"
        )
        session.commit()
        assert pending is not None
        user = session.exec(select(User)).one()
        credential = session.get(LocalCredential, user.user_id)
        assert credential is not None
        assert credential.password_hash
        assert "correct horse battery" not in credential.password_hash
        assert user.email_verified_at is None

        verify_token = _token_from_email(pending.body)
        assert local_auth.verify_email(session, verify_token)
        session.commit()
        assert not local_auth.verify_email(session, verify_token)  # one-time

        result = local_auth.authenticate_password(
            session, "person@example.org", "correct horse battery"
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
            "a different safe password",
            "a different safe password",
        )
        session.commit()
        assert not local_auth.reset_password(
            session,
            reset_token,
            "a different safe password",
            "a different safe password",
        )
        stored_session = session.exec(select(AuthSession)).one()
        assert stored_session.revoked_at is not None

    assert (
        local_auth.resolve_cookie_session(
            f"{cookie_name}={raw_session}", origin="http://localhost:3000"
        )
        is None
    )


def test_login_http_endpoint_sets_production_cookie_and_checks_origin(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, production=True)
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_auth.rx, "session", lambda: Session(engine))
    monkeypatch.setattr(auth_api.rx, "session", lambda: Session(engine))

    with Session(engine) as session:
        pending = local_auth.register_local_user(
            session, "person@example.org", "correct horse battery"
        )
        session.commit()
        assert pending is not None
        assert local_auth.verify_email(session, _token_from_email(pending.body))
        session.commit()

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
            "password": "correct horse battery",
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
