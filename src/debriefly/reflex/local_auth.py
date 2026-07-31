"""Local password, email-token, and opaque-session authentication primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import lru_cache
from http.cookies import SimpleCookie
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import ssl
from threading import BoundedSemaphore
from urllib.parse import urlparse

import reflex as rx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlmodel import Session, select

from debriefly.reflex.backend.models import (
    AuthSession,
    AuthToken,
    LocalCredential,
    User,
    UserIdentity,
)


logger = logging.getLogger(__name__)
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)
_PASSWORD_HASH_SLOTS = BoundedSemaphore(
    max(1, int(os.getenv("AUTH_PASSWORD_HASH_CONCURRENCY", "2")))
)

VERIFY_EMAIL = "verify_email"
PASSWORD_RESET = "password_reset"
PASSWORD_SETUP = "password_setup"


class AuthConfigurationError(RuntimeError):
    """Raised when production-safe authentication settings are absent."""


class InvalidPassword(ValueError):
    """Raised when a proposed password does not meet the local policy."""


@dataclass(frozen=True)
class AuthSettings:
    secret_key: str
    public_url: str
    api_public_url: str
    allowed_origins: tuple[str, ...]
    cookie_name: str
    cookie_secure: bool
    session_hours: int
    token_hours: int
    allow_registration: bool
    issuer: str


@dataclass(frozen=True)
class PendingEmail:
    recipient: str
    purpose: str
    subject: str
    body: str


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clean_origin(value: str) -> str:
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    public_url = os.getenv("AUTH_PUBLIC_URL", "http://localhost:3000").rstrip("/")
    api_public_url = os.getenv("AUTH_API_PUBLIC_URL", "").rstrip("/")
    secure_default = public_url.lower().startswith("https://")
    cookie_secure = _env_bool("AUTH_COOKIE_SECURE", secure_default)
    cookie_name = os.getenv("AUTH_COOKIE_NAME") or (
        "__Host-debriefly_session" if cookie_secure else "debriefly_session_dev"
    )
    origins = tuple(
        origin
        for origin in (
            _clean_origin(item)
            for item in os.getenv(
                "AUTH_ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
        )
        if origin
    )
    return AuthSettings(
        secret_key=os.getenv("AUTH_SECRET_KEY", ""),
        public_url=public_url,
        api_public_url=api_public_url,
        allowed_origins=origins,
        cookie_name=cookie_name,
        cookie_secure=cookie_secure,
        session_hours=max(1, int(os.getenv("AUTH_SESSION_HOURS", "168"))),
        token_hours=max(1, int(os.getenv("AUTH_TOKEN_HOURS", "48"))),
        allow_registration=_env_bool("AUTH_ALLOW_REGISTRATION", True),
        issuer=os.getenv("AUTH_ISSUER", "debriefly-local"),
    )


def require_auth_configuration() -> AuthSettings:
    settings = get_auth_settings()
    if len(settings.secret_key) < 32:
        raise AuthConfigurationError(
            "AUTH_SECRET_KEY must be an unpredictable value of at least 32 characters"
        )
    public_origin = _clean_origin(settings.public_url)
    if not public_origin:
        raise AuthConfigurationError("AUTH_PUBLIC_URL must be an absolute http(s) URL")
    public = urlparse(public_origin)
    is_local = (public.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
    if not is_local and (public.scheme != "https" or not settings.cookie_secure):
        raise AuthConfigurationError(
            "Non-local authentication requires HTTPS and AUTH_COOKIE_SECURE=true"
        )
    if public_origin not in settings.allowed_origins:
        raise AuthConfigurationError(
            "AUTH_ALLOWED_ORIGINS must include the AUTH_PUBLIC_URL origin"
        )
    if settings.cookie_secure and not settings.cookie_name.startswith("__Host-"):
        logger.warning("A secure auth cookie is configured without the __Host- prefix")
    if settings.cookie_name.startswith("__Host-") and not settings.cookie_secure:
        raise AuthConfigurationError("__Host- cookies require AUTH_COOKIE_SECURE=true")
    return settings


def auth_api_endpoint(name: str) -> str:
    """Return a browser-facing URL routed to the Reflex backend.

    Production should proxy ``/_event`` on the same public origin. Local
    development can set AUTH_API_PUBLIC_URL=http://localhost:8000.
    """
    settings = get_auth_settings()
    base = settings.api_public_url
    public = urlparse(settings.public_url)
    if not base and (public.hostname or "").lower() in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        # Reflex dev serves pages on :3000 and its FastAPI backend on :8000.
        # Native HTML forms do not receive Reflex's websocket URL rewrite.
        from reflex.config import get_config

        base = (get_config().api_url or "").rstrip("/")
    path = f"/_event/auth/{name.lstrip('/')}"
    return f"{base}{path}" if base else path


def auth_email_delivery_configured() -> bool:
    """Return whether verification/reset email can actually be delivered."""
    return bool(
        os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_FROM", "").strip()
    )


def frontend_url(path: str = "/") -> str:
    safe_path = safe_relative_path(path)
    return f"{get_auth_settings().public_url}{safe_path}"


def safe_relative_path(path: str | None, fallback: str = "/") -> str:
    value = (path or "").strip()
    if not value.startswith("/") or value.startswith("//"):
        return fallback
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or "\\" in value:
        return fallback
    return value


def origin_is_allowed(origin: str | None) -> bool:
    cleaned = _clean_origin(origin or "")
    settings = get_auth_settings()
    return bool(cleaned) and any(
        hmac.compare_digest(cleaned, allowed) for allowed in settings.allowed_origins
    )


def normalize_email(email: str) -> str:
    value = (email or "").strip().casefold()
    if len(value) > 320 or not _EMAIL_PATTERN.fullmatch(value):
        raise ValueError("Enter a valid email address.")
    local, domain = value.rsplit("@", 1)
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Enter a valid email address.") from exc
    normalized = f"{local}@{domain}"
    if len(normalized) > 320:
        raise ValueError("Enter a valid email address.")
    return normalized


def validate_password(password: str) -> None:
    if len(password or "") < 12:
        raise InvalidPassword("Use at least 12 characters.")
    if len(password) > 1024:
        raise InvalidPassword("Password is too long.")


def hash_password(password: str) -> str:
    validate_password(password)
    return _argon_hash(password)


def _argon_hash(password: str) -> str:
    # Argon2 deliberately consumes memory. Bound concurrent work per process so
    # an authentication burst cannot exhaust the application container.
    with _PASSWORD_HASH_SLOTS:
        return _PASSWORD_HASHER.hash(password)


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    return _argon_hash(secrets.token_urlsafe(32))


def _verify_password(encoded: str | None, password: str) -> bool:
    candidate = encoded or _dummy_password_hash()
    try:
        with _PASSWORD_HASH_SLOTS:
            return _PASSWORD_HASHER.verify(candidate, password or "")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_digest(raw_token: str) -> str:
    settings = require_auth_configuration()
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _new_internal_user_id(session: Session) -> str:
    for _ in range(5):
        user_id = f"usr_{secrets.token_urlsafe(18)}"
        if session.get(User, user_id) is None:
            return user_id
    raise RuntimeError("Could not allocate a unique user ID")


def _issue_token(
    session: Session,
    user: User,
    purpose: str,
    *,
    email_normalized: str | None = None,
) -> str:
    # Consumers lock User -> AuthToken. Issuance must use the same order so a
    # concurrent email request and token submission cannot deadlock.
    locked_user = session.exec(
        select(User)
        .where(User.user_id == user.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if locked_user is None:
        raise RuntimeError("Cannot issue an authentication token for a missing user")
    user = locked_user
    raw_token = secrets.token_urlsafe(32)
    now = _now()
    # A newly issued link supersedes every older link for the same operation.
    for existing in session.exec(
        select(AuthToken).where(
            AuthToken.user_id == user.user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    ):
        existing.used_at = now
        session.add(existing)
    session.add(
        AuthToken(
            user_id=user.user_id,
            purpose=purpose,
            token_digest=_token_digest(raw_token),
            email_normalized=email_normalized,
            created_at=now,
            expires_at=now + timedelta(hours=get_auth_settings().token_hours),
        )
    )
    return raw_token


def _recent_token_exists(session: Session, user_id: str, purpose: str) -> bool:
    cutoff = _now() - timedelta(minutes=5)
    latest = session.exec(
        select(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .order_by(AuthToken.created_at.desc())
    ).first()
    return latest is not None and (_aware(latest.created_at) or cutoff) >= cutoff


def _email_link(path: str, raw_token: str) -> str:
    separator = "&" if "?" in path else "?"
    return frontend_url(f"{path}{separator}token={raw_token}")


def register_local_user(
    session: Session,
    email: str,
) -> PendingEmail | None:
    settings = require_auth_configuration()
    if not settings.allow_registration:
        raise PermissionError("New account registration is disabled.")
    normalized = normalize_email(email)
    existing = session.exec(
        select(User)
        .where(User.email_normalized == normalized)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()

    if existing is not None:
        # Keep registration responses non-enumerating. Only a pending account
        # created by local registration may receive another verification link.
        identity = session.exec(
            select(UserIdentity).where(
                UserIdentity.user_id == existing.user_id,
                UserIdentity.provider == "local",
                UserIdentity.issuer == settings.issuer,
                UserIdentity.link_source == "registration",
                UserIdentity.email_normalized == normalized,
            )
        ).first()
        if (
            existing.status != "pending"
            or existing.email_verified_at is not None
            or identity is None
            or _recent_token_exists(session, existing.user_id, VERIFY_EMAIL)
        ):
            return None
        raw_token = _issue_token(
            session, existing, VERIFY_EMAIL, email_normalized=normalized
        )
    else:
        now = _now()
        user = User(
            user_id=_new_internal_user_id(session),
            email_normalized=normalized,
            email_verified_at=None,
            status="pending",
            role="user",
            auth_version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            UserIdentity(
                user_id=user.user_id,
                provider="local",
                issuer=settings.issuer,
                subject=normalized,
                email=normalized,
                email_normalized=normalized,
                link_source="registration",
            )
        )
        raw_token = _issue_token(
            session, user, VERIFY_EMAIL, email_normalized=normalized
        )

    # Verification is confirmed by a native POST on the frontend page. A GET
    # must not activate the account because email security scanners follow links.
    link = _email_link("/verify-email", raw_token)
    return PendingEmail(
        recipient=normalized,
        purpose=VERIFY_EMAIL,
        subject="Verify your Debriefly account",
        body=(
            "Verify your Debriefly email address and choose your password using "
            "this one-time link:\n\n"
            f"{link}\n\nThis link expires in {settings.token_hours} hours. "
            "No password is active until you complete this step."
        ),
    )


def request_password_email(session: Session, email: str) -> PendingEmail | None:
    normalized = normalize_email(email)
    user = session.exec(
        select(User)
        .where(User.email_normalized == normalized)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if user is None or user.email_verified_at is None or user.status != "active":
        return None
    credential = session.get(LocalCredential, user.user_id)
    purpose = (
        PASSWORD_RESET if credential and credential.password_hash else PASSWORD_SETUP
    )
    if _recent_token_exists(session, user.user_id, purpose):
        return None
    raw_token = _issue_token(session, user, purpose, email_normalized=normalized)
    settings = get_auth_settings()
    link = _email_link("/reset-password", raw_token)
    label = "Set up" if purpose == PASSWORD_SETUP else "Reset"
    return PendingEmail(
        recipient=normalized,
        purpose=purpose,
        subject=f"{label} your Debriefly password",
        body=(
            f"{label} your Debriefly password using this one-time link:\n\n"
            f"{link}\n\nThis link expires in {settings.token_hours} hours."
        ),
    )


def verify_email(
    session: Session,
    raw_token: str,
    password: str,
    confirmation: str,
) -> bool:
    validate_password(password)
    if not hmac.compare_digest(password, confirmation):
        raise InvalidPassword("Passwords do not match.")
    settings = require_auth_configuration()
    locked = _locked_valid_token_and_user(session, raw_token, {VERIFY_EMAIL})
    if locked is None:
        return False
    token, user = locked
    if (
        user is None
        or user.status != "pending"
        or user.email_verified_at is not None
        or user.email_normalized != token.email_normalized
    ):
        return False
    identity = session.exec(
        select(UserIdentity)
        .where(
            UserIdentity.user_id == user.user_id,
            UserIdentity.provider == "local",
            UserIdentity.issuer == settings.issuer,
            UserIdentity.link_source == "registration",
            UserIdentity.email_normalized == user.email_normalized,
        )
        .with_for_update()
    ).first()
    if identity is None:
        return False

    # Hash only after the one-time token and its pending local identity have
    # been validated. Overwriting an old pending hash also repairs accounts
    # created by the pre-email-first registration flow.
    password_hash = _argon_hash(password)
    now = _now()
    token.used_at = now
    user.email_verified_at = now
    user.status = "active"
    user.auth_version += 1
    user.updated_at = now
    identity.email_verified_at = now
    credential = session.exec(
        select(LocalCredential)
        .where(LocalCredential.user_id == user.user_id)
        .with_for_update()
    ).first()
    if credential is None:
        credential = LocalCredential(user_id=user.user_id)
    credential.password_hash = password_hash
    credential.password_changed_at = now
    credential.failed_attempts = 0
    credential.locked_until = None
    for auth_session in session.exec(
        select(AuthSession).where(
            AuthSession.user_id == user.user_id,
            AuthSession.revoked_at.is_(None),
        )
    ):
        auth_session.revoked_at = now
        session.add(auth_session)
    session.add(token)
    session.add(user)
    session.add(identity)
    session.add(credential)
    return True


def reset_password(
    session: Session,
    raw_token: str,
    password: str,
    confirmation: str,
) -> bool:
    validate_password(password)
    if not hmac.compare_digest(password, confirmation):
        raise InvalidPassword("Passwords do not match.")
    locked = _locked_valid_token_and_user(
        session,
        raw_token,
        {PASSWORD_RESET, PASSWORD_SETUP},
    )
    if locked is None:
        return False
    token, user = locked
    if (
        user is None
        or user.status != "active"
        or user.email_verified_at is None
        or user.email_normalized != token.email_normalized
    ):
        return False
    now = _now()
    credential = session.exec(
        select(LocalCredential)
        .where(LocalCredential.user_id == user.user_id)
        .with_for_update()
    ).first()
    if token.purpose == PASSWORD_RESET and (
        credential is None or not credential.password_hash
    ):
        return False
    if token.purpose == PASSWORD_SETUP and credential and credential.password_hash:
        return False
    if credential is None:
        credential = LocalCredential(user_id=user.user_id)
    credential.password_hash = _argon_hash(password)
    credential.password_changed_at = now
    credential.failed_attempts = 0
    credential.locked_until = None
    token.used_at = now
    user.auth_version += 1
    user.updated_at = now
    for sibling in session.exec(
        select(AuthToken).where(
            AuthToken.user_id == user.user_id,
            AuthToken.used_at.is_(None),
        )
    ):
        sibling.used_at = now
        session.add(sibling)
    for auth_session in session.exec(
        select(AuthSession).where(
            AuthSession.user_id == user.user_id,
            AuthSession.revoked_at.is_(None),
        )
    ):
        auth_session.revoked_at = now
        session.add(auth_session)
    session.add(credential)
    session.add(token)
    session.add(user)
    return True


def _locked_valid_token_and_user(
    session: Session,
    raw_token: str,
    purposes: set[str],
) -> tuple[AuthToken, User] | None:
    """Lock a token's user first, then the token, and revalidate both rows.

    A consistent user-before-token lock order makes one-time consumption safe
    when two different links for the same account are submitted concurrently.
    """
    if not raw_token or len(raw_token) > 512:
        return None
    digest = _token_digest(raw_token)
    candidate_user_id = session.exec(
        select(AuthToken.user_id).where(
            AuthToken.token_digest == digest,
            AuthToken.purpose.in_(purposes),
            AuthToken.used_at.is_(None),
        )
    ).first()
    if candidate_user_id is None:
        return None
    user = session.exec(
        select(User).where(User.user_id == candidate_user_id).with_for_update()
    ).first()
    if user is None:
        return None
    token = session.exec(
        select(AuthToken)
        .where(
            AuthToken.token_digest == digest,
            AuthToken.user_id == user.user_id,
            AuthToken.purpose.in_(purposes),
            AuthToken.used_at.is_(None),
        )
        .with_for_update()
    ).first()
    if token is None:
        return None
    expires_at = _aware(token.expires_at)
    if expires_at is None or expires_at <= _now():
        return None
    return token, user


def authenticate_password(
    session: Session,
    email: str,
    password: str,
) -> tuple[User, str] | None:
    try:
        normalized = normalize_email(email)
    except ValueError:
        _verify_password(None, password)
        return None
    user = session.exec(select(User).where(User.email_normalized == normalized)).first()
    credential = session.get(LocalCredential, user.user_id) if user else None
    now = _now()
    locked_until = _aware(credential.locked_until) if credential else None
    if locked_until and locked_until > now:
        _verify_password(None, password)
        return None

    verified = _verify_password(
        credential.password_hash if credential else None,
        password,
    )
    if not verified:
        if credential is not None:
            credential.failed_attempts += 1
            if credential.failed_attempts >= 8:
                credential.locked_until = now + timedelta(minutes=15)
                credential.failed_attempts = 0
            session.add(credential)
        return None

    if (
        user is None
        or credential is None
        or user.status != "active"
        or user.email_verified_at is None
    ):
        return None

    credential.failed_attempts = 0
    credential.locked_until = None
    if _PASSWORD_HASHER.check_needs_rehash(credential.password_hash):
        credential.password_hash = _argon_hash(password)
    session.add(credential)

    settings = require_auth_configuration()
    raw_session = secrets.token_urlsafe(32)
    active_sessions = session.exec(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.created_at.desc())
    ).all()
    # Bound active sessions per account while allowing normal multi-device use.
    for old_session in active_sessions[19:]:
        old_session.revoked_at = now
        session.add(old_session)
    session.add(
        AuthSession(
            user_id=user.user_id,
            token_digest=_token_digest(raw_session),
            auth_version=user.auth_version,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_hours),
        )
    )
    return user, raw_session


def _cookie_value(cookie_header: str, cookie_name: str) -> str:
    if not cookie_header or len(cookie_header) > 16_384:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return ""
    morsel = cookie.get(cookie_name)
    return morsel.value if morsel is not None else ""


def resolve_cookie_session(cookie_header: str, *, origin: str) -> User | None:
    """Return the active user for a websocket handshake cookie."""
    if not origin_is_allowed(origin):
        return None
    try:
        settings = require_auth_configuration()
        raw_token = _cookie_value(cookie_header, settings.cookie_name)
        if not raw_token:
            return None
        digest = _token_digest(raw_token)
    except AuthConfigurationError:
        logger.error("Local authentication is not configured")
        return None

    now = _now()
    with rx.session() as session:
        auth_session = session.exec(
            select(AuthSession).where(AuthSession.token_digest == digest)
        ).first()
        if auth_session is None or auth_session.revoked_at is not None:
            return None
        expires_at = _aware(auth_session.expires_at)
        if expires_at is None or expires_at <= now:
            auth_session.revoked_at = now
            session.add(auth_session)
            session.commit()
            return None
        user = session.get(User, auth_session.user_id)
        if (
            user is None
            or user.status != "active"
            or auth_session.auth_version != user.auth_version
        ):
            auth_session.revoked_at = now
            session.add(auth_session)
            session.commit()
            return None
        last_seen = _aware(auth_session.last_seen_at)
        if last_seen is None or last_seen <= now - timedelta(minutes=5):
            auth_session.last_seen_at = now
            session.add(auth_session)
            session.commit()
            # Session.commit() expires every loaded ORM object by default.
            # Reload the profile before detaching it so middleware can safely
            # read its scalar attributes after this context closes.
            session.refresh(user)
        # Detach the non-sensitive user profile before the DB session closes.
        session.expunge(user)
        return user


def revoke_cookie_session(session: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    try:
        digest = _token_digest(raw_token)
    except AuthConfigurationError:
        return
    auth_session = session.exec(
        select(AuthSession).where(AuthSession.token_digest == digest)
    ).first()
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = _now()
        session.add(auth_session)


def send_smtp_email(message: PendingEmail | None) -> bool:
    """Send one plain-text email without logging its contents."""
    if message is None:
        return True
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not auth_email_delivery_configured():
        logger.error("SMTP_HOST and SMTP_FROM are required to send email")
        return False
    port = int(os.getenv("SMTP_PORT", "465" if _env_bool("SMTP_SSL", False) else "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    use_ssl = _env_bool("SMTP_SSL", False)
    starttls = _env_bool("SMTP_STARTTLS", not use_ssl)

    email = EmailMessage()
    email["From"] = sender
    email["To"] = message.recipient
    email["Subject"] = message.subject
    email.set_content(message.body)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_class(host, port, timeout=15) as client:
            if starttls:
                client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, password)
            client.send_message(email)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send email")
        return False


def send_auth_email(message: PendingEmail | None) -> bool:
    """Send one auth email without ever logging its one-time link."""
    return send_smtp_email(message)


def invalidate_unsent_email(message: PendingEmail | None) -> None:
    """Invalidate a just-issued link if its email could not be delivered."""
    if message is None:
        return
    try:
        normalized = normalize_email(message.recipient)
    except ValueError:
        return
    with rx.session() as session:
        user = session.exec(
            select(User).where(User.email_normalized == normalized)
        ).first()
        if user is None:
            return
        token = session.exec(
            select(AuthToken)
            .where(
                AuthToken.user_id == user.user_id,
                AuthToken.purpose == message.purpose,
                AuthToken.used_at.is_(None),
            )
            .order_by(AuthToken.created_at.desc())
        ).first()
        if token is not None:
            token.used_at = _now()
            session.add(token)
            session.commit()
