import asyncio
import reflex as rx
from sqlmodel import select
import logging
import reflex_clerk as clerk
from debriefly.openai import DEFAULT_OPENAI_MODEL
from debriefly.reflex.backend.models import Config, User, Form, UserOpenAISettings


logger = logging.getLogger(__name__)


class MainState(rx.State):
    TOS_VERSION = "2025-06-19"
    _user_id: str = ""
    user: User = User()
    base_url: str = ""
    config: dict[str, str] = {}
    config_loaded: bool = False
    config_loading: bool = False
    openai_api_key_configured: bool = False
    openai_model: str = DEFAULT_OPENAI_MODEL

    def _user_has_access(self, form: Form | None = None):
        if form is None and hasattr(self, "form"):
            form = self.form
        return form is not None and form.user_id == self.user_id

    def _consent_redirect_if_needed(self):
        if (
            self.user.tos_version != self.TOS_VERSION
            and self.router.page.path != "/consent"
        ):
            return rx.redirect("/consent")

    async def sync_user_from_clerk(self) -> bool:
        clerk_state = await self.get_state(clerk.ClerkState)
        if clerk_state.user_id is None:
            return False

        if self._user_id != clerk_state.user_id:
            self._user_id = clerk_state.user_id
            await self._ensure_user_record()
        elif getattr(self.user, "user_id", None) != self._user_id:
            await self._ensure_user_record()

        self.load_openai_settings_status()
        return True

    async def wait_for_user(self):
        if not await self.sync_user_from_clerk():  # still logging in
            await asyncio.sleep(0.25)  # 250 ms pause
            return MainState.wait_for_user()  # schedule myself again

        await self.load_config()
        return self._consent_redirect_if_needed()

    # 2 ─ Helper that mirrors the body of your old load_user()
    async def _ensure_user_record(self):
        with rx.session() as s:
            db_user = s.exec(select(User).where(User.user_id == self._user_id)).first()
            if db_user is None:  # new respondent
                db_user = User(user_id=self._user_id)
                s.add(db_user)
                s.commit()
            self.user = db_user

    # 3 ─ Call wait_for_user once from every page
    async def init(self):
        if await self.sync_user_from_clerk():
            await self.load_config()
            return self._consent_redirect_if_needed()

        return MainState.wait_for_user()

    @rx.var(cache=True)
    def user_id(self) -> str:
        return self._user_id

    async def load_config(self, force: bool = False):
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
                    logger.info("Loading config: %s", config.name)
                    config_values[config.name] = config.value
                    if config.name == "BASE_URL":
                        base_url = config.value
                self.config = config_values
                self.base_url = base_url
                self.config_loaded = True
        finally:
            self.config_loading = False

    def load_openai_settings_status(self):
        if not self._user_id:
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
        state = await self.get_state(clerk.ClerkState)
        if state.user_id is None:
            # user_id not (yet) available from clerk
            # this does happen when on_load is finished before ClerkState
            # has the user_id loaded. In this case, do nothing.
            return
        self._user_id = state.user_id

        with rx.session() as session:
            user = session.exec(
                select(User).where(User.user_id == self.user_id)
            ).first()
            if user is None:
                logger.info(f"Saving user {self.user_id}")
                user = User(user_id=self.user_id)
                session.add(user)
                session.commit()
                self.user = session.exec(
                    select(User).where(User.user_id == self.user_id)
                ).first()
            else:
                self.user = user

        self.load_openai_settings_status()

        if (
            self.user.tos_version != self.TOS_VERSION
            and self.router.page.path != "/consent"
        ):
            return rx.redirect("/consent")

    async def update_config(self, form_data: dict):
        main_state = await self.get_state(MainState)
        with rx.session() as session:
            for key, value in form_data.items():
                config = session.exec(select(Config).where(Config.name == key)).first()
                if config is not None:
                    config.value = value
            session.commit()
            await main_state.load_config(force=True)
        return rx.toast.success("Config updated successfully")

    async def update_user(self, form_data: dict):
        for field in User.get_fields():
            if field != "id" and field in form_data:
                setattr(self.user, field, form_data[field])
        with rx.session() as session:
            session.add(self.user)
            session.commit()
            await self.load_user()
        return rx.toast.success("User updated successfully")
