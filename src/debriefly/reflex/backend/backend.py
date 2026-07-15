import logging
from urllib.parse import quote

import reflex as rx
from sqlmodel import select

from debriefly.openai import DEFAULT_OPENAI_MODEL
from debriefly.reflex.backend.models import Config, Form, User, UserOpenAISettings


logger = logging.getLogger(__name__)


class MainState(rx.State):
    """Shared state for researcher-only pages.

    Authentication is resolved from a revocable, server-side session on every
    protected event. Only the non-sensitive ``User`` profile is exposed here;
    password hashes and session tokens live in separate database models.
    """

    TOS_VERSION = "2025-06-19"
    _user_id: str = ""
    user: User = User()
    auth_checked: bool = False
    is_authenticated: bool = False
    base_url: str = ""
    config: dict[str, str] = {}
    config_loaded: bool = False
    config_loading: bool = False
    openai_api_key_configured: bool = False
    openai_model: str = DEFAULT_OPENAI_MODEL

    def _set_authenticated_user(self, user: User) -> None:
        self._user_id = user.user_id
        self.user = user
        self.is_authenticated = True
        self.auth_checked = True

    def _clear_authentication(self) -> None:
        self._user_id = ""
        self.user = User()
        self.is_authenticated = False
        self.auth_checked = True
        self.openai_api_key_configured = False
        self.openai_model = DEFAULT_OPENAI_MODEL
        self.config = {}
        self.config_loaded = False

    def _user_has_access(self, form: Form | None = None) -> bool:
        if form is None and hasattr(self, "form"):
            form = self.form
        return (
            self.is_authenticated and form is not None and form.user_id == self.user_id
        )

    def _consent_redirect_if_needed(self):
        if (
            self.is_authenticated
            and self.user.tos_version != self.TOS_VERSION
            and self.router.page.path != "/consent"
        ):
            return rx.redirect("/consent")

    async def sync_user_from_session(self) -> bool:
        """Resolve the HttpOnly browser cookie against the session database."""
        from debriefly.reflex.local_auth import resolve_cookie_session

        cookie_header = getattr(self.router.headers, "cookie", "")
        origin = getattr(self.router.headers, "origin", "")
        user = resolve_cookie_session(cookie_header, origin=origin)
        if user is None:
            self._clear_authentication()
            return False

        if self._user_id != user.user_id:
            # Clear identity-specific cached values before switching users in a tab.
            self.config = {}
            self.config_loaded = False
            self.openai_api_key_configured = False
            self.openai_model = DEFAULT_OPENAI_MODEL

        self._set_authenticated_user(user)
        self.load_openai_settings_status()
        return True

    async def _ensure_user_record(self) -> bool:
        """Reload the current user without creating identities implicitly."""
        if not self._user_id:
            return False
        with rx.session() as session:
            user = session.get(User, self._user_id)
            if user is None:
                self._clear_authentication()
                return False
            self._set_authenticated_user(user)
            return True

    async def init(self):
        """Initialize a protected page, or send the browser to local sign-in."""
        if not await self.sync_user_from_session():
            path = self.router.page.raw_path or self.router.page.path or "/"
            next_path = (
                path if path.startswith("/") and not path.startswith("//") else "/"
            )
            return rx.redirect(f"/signin?next={quote(next_path, safe='/')}")

        await self.load_config()
        return self._consent_redirect_if_needed()

    async def init_admin(self):
        redirect = await self.init()
        if redirect is not None:
            return redirect
        if not self.is_admin:
            return rx.redirect("/")

    @rx.var(cache=True)
    def user_id(self) -> str:
        return self._user_id

    @rx.var(cache=True)
    def is_admin(self) -> bool:
        return self.is_authenticated and getattr(self.user, "role", "user") == "admin"

    async def load_config(self, force: bool = False):
        if not self.is_authenticated:
            return
        if self.config_loaded and not force:
            return
        if self.config_loading and not force:
            return

        logger.info("Loading config")
        self.config_loading = True
        try:
            with rx.session() as session:
                config_values = {}
                base_url = self.base_url
                for config in session.exec(select(Config)):
                    if config.name != "BASE_URL":
                        continue
                    config_values[config.name] = config.value
                    base_url = config.value
                self.config = config_values
                self.base_url = base_url
                self.config_loaded = True
        finally:
            self.config_loading = False

    def load_openai_settings_status(self):
        if not self.is_authenticated or not self._user_id:
            self.openai_api_key_configured = False
            self.openai_model = DEFAULT_OPENAI_MODEL
            return

        with rx.session() as session:
            settings = UserOpenAISettings.get_for_user(session, self._user_id)
            self.openai_api_key_configured = bool(
                settings is not None and settings.is_configured
            )
            self.openai_model = (
                settings.model if settings is not None else DEFAULT_OPENAI_MODEL
            )

    async def load_user(self):
        """Compatibility entry point for states that need a fresh local session."""
        if not await self.sync_user_from_session():
            return rx.redirect("/signin")
        return self._consent_redirect_if_needed()

    async def update_config(self, form_data: dict):
        if not await self.sync_user_from_session() or not self.is_admin:
            return rx.toast.error("Administrator access is required.")

        # Global configuration has a deliberately small server-side allowlist.
        allowed_keys = {"BASE_URL"}
        with rx.session() as session:
            for key, value in form_data.items():
                if key not in allowed_keys:
                    continue
                config = session.exec(select(Config).where(Config.name == key)).first()
                if config is not None:
                    config.value = str(value)
            session.commit()
        await self.load_config(force=True)
        return rx.toast.success("Config updated successfully")

    async def update_user(self, form_data: dict):
        # Authentication metadata is never mass-assigned from browser input.
        return rx.toast.error("No editable profile fields were submitted.")
