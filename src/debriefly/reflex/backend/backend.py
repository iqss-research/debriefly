import reflex as rx
from sqlmodel import select
import logging
import reflex_clerk as clerk
from debriefly.reflex.backend.models import Config, User, Form


logger = logging.getLogger(__name__)


class MainState(rx.State):
    _user_id: str = ""

    user: User = User()
    base_url: str = ""
    config: dict[str, str] = {}

    def _user_has_access(self, form: Form | None = None):
        if form is None and hasattr(self, "form"):
            form = self.form
        return form is not None and form.user_id == self.user_id

    async def init(self):
        logger.info("Initializing MainState")
        await self.load_config()
        await self.load_user()

    @rx.var(cache=True)
    def user_id(self) -> str:
        return self._user_id

    async def load_config(self):
        logger.info("Loading config")
        with rx.session() as session:
            for config in session.exec(select(Config)):
                logger.info("Loading config: %s", config.name)
                self.config[config.name] = config.value
                if config.name == "BASE_URL":
                    self.base_url = config.value

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

    async def update_config(self, form_data: dict):
        main_state = await self.get_state(MainState)
        with rx.session() as session:
            for key, value in form_data.items():
                config = session.exec(select(Config).where(Config.name == key)).first()
                if config is not None:
                    config.value = value
            session.commit()
            await main_state.init()
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
