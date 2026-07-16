"""FastAPI endpoints that create and remove HttpOnly auth cookies."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Annotated
from urllib.parse import urlencode
import hashlib
import logging

import reflex as rx
from fastapi import FastAPI, Form, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError

from debriefly.reflex.local_auth import (
    AuthConfigurationError,
    InvalidPassword,
    auth_email_delivery_configured,
    authenticate_password,
    frontend_url,
    get_auth_settings,
    invalidate_unsent_email,
    origin_is_allowed,
    register_local_user,
    request_password_email,
    reset_password,
    revoke_cookie_session,
    safe_relative_path,
    send_auth_email,
    verify_email,
)


logger = logging.getLogger(__name__)
_AUTH_PREFIX = "/_event/auth"
_attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_attempts_lock = Lock()


def _limited(
    request: Request,
    bucket: str,
    limit: int,
    seconds: int,
    *,
    identifier: str = "",
) -> bool:
    """Bound obvious bursts; account locks provide the durable login control."""
    now = datetime.now(timezone.utc).timestamp()
    client = request.client.host if request.client else "unknown"
    identifier_digest = hashlib.sha256(
        identifier.strip().casefold().encode("utf-8")
    ).hexdigest()[:24]
    key = (bucket, f"{client}:{identifier_digest}")
    with _attempts_lock:
        if key not in _attempts and len(_attempts) >= 50_000:
            # Bound per-worker memory under a rotating-identifier attack. The
            # durable per-account lock remains authoritative across workers.
            _attempts.pop(next(iter(_attempts)))
        entries = _attempts[key]
        while entries and entries[0] <= now - seconds:
            entries.popleft()
        if len(entries) >= limit:
            return True
        entries.append(now)
        return False


def _post_allowed(request: Request) -> bool:
    return origin_is_allowed(request.headers.get("origin"))


def _redirect(path: str, **query: str) -> RedirectResponse:
    suffix = f"?{urlencode(query)}" if query else ""
    response = RedirectResponse(frontend_url(f"{path}{suffix}"), status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _forbidden() -> PlainTextResponse:
    return PlainTextResponse(
        "Forbidden",
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )


def _promote_routes_before_event_mount(api: FastAPI) -> None:
    """Ensure exact auth routes win before Reflex's ``/_event`` Socket.IO mount."""
    routes = list(api.router.routes)
    auth_routes = [
        route
        for route in routes
        if getattr(route, "path", "").startswith(f"{_AUTH_PREFIX}/")
    ]
    if not auth_routes:
        return
    remaining = [route for route in routes if route not in auth_routes]
    mount_index = next(
        (
            index
            for index, route in enumerate(remaining)
            if getattr(route, "path", "") == "/_event"
        ),
        len(remaining),
    )
    api.router.routes[:] = (
        remaining[:mount_index] + auth_routes + remaining[mount_index:]
    )


def register_auth_routes(api: FastAPI) -> None:
    """Register native HTTP forms on the Reflex backend once."""
    if any(
        getattr(route, "path", "") == f"{_AUTH_PREFIX}/login"
        for route in api.router.routes
    ):
        return

    @api.post(f"{_AUTH_PREFIX}/login", include_in_schema=False)
    def login(
        request: Request,
        email: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        next_path: Annotated[str, Form(alias="next")] = "/",
    ):
        if not _post_allowed(request):
            return _forbidden()
        if len(email) > 320 or len(password) > 1024:
            return _redirect("/signin", error="invalid")
        if _limited(request, "login", 20, 5 * 60, identifier=email):
            return _redirect("/signin", error="rate-limited")
        try:
            with rx.session() as session:
                result = authenticate_password(session, email, password)
                session.commit()
        except AuthConfigurationError:
            logger.exception("Local authentication is not configured")
            return _redirect("/signin", error="configuration")
        if result is None:
            return _redirect("/signin", error="invalid")

        _, raw_session = result
        settings = get_auth_settings()
        response = _redirect(safe_relative_path(next_path))
        response.set_cookie(
            key=settings.cookie_name,
            value=raw_session,
            max_age=settings.session_hours * 60 * 60,
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    @api.post(f"{_AUTH_PREFIX}/register", include_in_schema=False)
    def register(
        request: Request,
        email: Annotated[str, Form()] = "",
    ):
        if not _post_allowed(request):
            return _forbidden()
        if not auth_email_delivery_configured():
            return _redirect("/register", error="email-not-configured")
        if len(email) > 320:
            return _redirect("/register", error="invalid-input")
        if _limited(request, "register-ip", 30, 60 * 60):
            return _redirect("/register", error="rate-limited")
        if _limited(request, "register", 6, 60 * 60, identifier=email):
            return _redirect("/register", error="rate-limited")
        try:
            with rx.session() as session:
                pending = register_local_user(session, email)
                session.commit()
        except ValueError:
            return _redirect("/register", error="invalid-input")
        except PermissionError:
            return _redirect("/register", error="disabled")
        except AuthConfigurationError:
            logger.exception("Local authentication is not configured")
            return _redirect("/register", error="configuration")
        except IntegrityError:
            # A concurrent registration for the same normalized email is treated
            # exactly like an existing account to avoid account enumeration.
            return _redirect("/signin", notice="check-email")

        sent = send_auth_email(pending)
        if pending is not None and not sent:
            invalidate_unsent_email(pending)
        return _redirect("/signin", notice="check-email")

    @api.post(f"{_AUTH_PREFIX}/forgot-password", include_in_schema=False)
    def forgot_password(
        request: Request,
        email: Annotated[str, Form()] = "",
    ):
        if not _post_allowed(request):
            return _forbidden()
        if not auth_email_delivery_configured():
            return _redirect("/forgot-password", error="email-not-configured")
        if len(email) > 320:
            return _redirect("/signin", notice="password-email")
        if _limited(request, "forgot", 10, 60 * 60, identifier=email):
            return _redirect("/forgot-password", error="rate-limited")
        pending = None
        try:
            with rx.session() as session:
                pending = request_password_email(session, email)
                session.commit()
        except (ValueError, AuthConfigurationError):
            # Keep this endpoint non-enumerating, including malformed addresses.
            pass
        if pending is not None and not send_auth_email(pending):
            invalidate_unsent_email(pending)
        return _redirect("/signin", notice="password-email")

    @api.post(f"{_AUTH_PREFIX}/verify", include_in_schema=False)
    def verify(
        request: Request,
        token: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        password_confirm: Annotated[str, Form()] = "",
    ):
        if not _post_allowed(request):
            return _forbidden()
        if len(token) > 512:
            return _redirect("/signin", error="invalid-link")
        if len(password) > 1024 or len(password_confirm) > 1024:
            return _redirect("/verify-email", token=token, error="invalid-password")
        if _limited(request, "verify", 20, 60 * 60, identifier=token):
            return _redirect("/verify-email", token=token, error="rate-limited")
        success = False
        try:
            with rx.session() as session:
                success = verify_email(
                    session,
                    token,
                    password,
                    password_confirm,
                )
                session.commit()
        except (InvalidPassword, ValueError):
            return _redirect("/verify-email", token=token, error="invalid-password")
        except AuthConfigurationError:
            logger.exception("Local authentication is not configured")
            return _redirect("/verify-email", token=token, error="configuration")
        if not success:
            return _redirect("/signin", error="invalid-link")
        return _redirect("/signin", notice="verified")

    @api.post(f"{_AUTH_PREFIX}/reset-password", include_in_schema=False)
    def reset(
        request: Request,
        token: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        password_confirm: Annotated[str, Form()] = "",
    ):
        if not _post_allowed(request):
            return _forbidden()
        if len(token) > 512 or len(password) > 1024 or len(password_confirm) > 1024:
            return _redirect("/reset-password", error="invalid-link")
        if _limited(request, "reset", 20, 60 * 60, identifier=token):
            return _redirect("/reset-password", error="rate-limited")
        try:
            with rx.session() as session:
                success = reset_password(session, token, password, password_confirm)
                session.commit()
        except (InvalidPassword, ValueError):
            return _redirect(
                "/reset-password",
                token=token,
                error="invalid-password",
            )
        except AuthConfigurationError:
            logger.exception("Local authentication is not configured")
            return _redirect("/reset-password", error="configuration")
        if not success:
            return _redirect("/reset-password", error="invalid-link")
        return _redirect("/signin", notice="password-updated")

    @api.post(f"{_AUTH_PREFIX}/logout", include_in_schema=False)
    def logout(request: Request):
        if not _post_allowed(request):
            return _forbidden()
        settings = get_auth_settings()
        with rx.session() as session:
            revoke_cookie_session(session, request.cookies.get(settings.cookie_name))
            session.commit()
        response = _redirect("/signin", notice="signed-out")
        response.delete_cookie(
            key=settings.cookie_name,
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    _promote_routes_before_event_mount(api)
