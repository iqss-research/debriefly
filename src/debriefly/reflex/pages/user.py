from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import UserOpenAISettings
from debriefly.openai import DEFAULT_OPENAI_MODEL
import reflex as rx


class UserSettingsState(MainState):
    api_key_status: str = "No API key saved"
    model_input: str = DEFAULT_OPENAI_MODEL

    async def load_settings(self):
        if not await self.sync_user_from_clerk():
            return

        with rx.session() as session:
            settings = UserOpenAISettings.get_for_user(session, self.user_id)
            if settings is None:
                self.api_key_status = "No API key saved"
                self.model_input = DEFAULT_OPENAI_MODEL
            else:
                self.api_key_status = "API key saved"
                self.model_input = settings.model or DEFAULT_OPENAI_MODEL

        self.load_openai_settings_status()

    def set_model_input(self, value: str):
        self.model_input = value

    async def update_openai_settings(self, form_data: dict[str, str]):
        if not await self.sync_user_from_clerk():
            return rx.toast.error("Please sign in before saving your OpenAI key.")

        api_key = (form_data.get("openai_api_key") or "").strip()
        model = (form_data.get("openai_model") or DEFAULT_OPENAI_MODEL).strip()

        with rx.session() as session:
            settings = UserOpenAISettings.get_for_user(session, self.user_id)
            if settings is None:
                if not api_key:
                    return rx.toast.error("Enter an OpenAI API key before saving.")
                settings = UserOpenAISettings(
                    user_id=self.user_id,
                    api_key=api_key,
                    model=model,
                )
            else:
                if api_key:
                    settings.api_key = api_key
                settings.model = model

            session.add(settings)
            session.commit()

        await self.load_settings()
        return rx.toast.success("OpenAI settings updated successfully.")

    async def clear_openai_api_key(self):
        if not await self.sync_user_from_clerk():
            return rx.toast.error("Please sign in before removing your OpenAI key.")

        with rx.session() as session:
            settings = UserOpenAISettings.get_for_user(session, self.user_id)
            if settings is not None:
                session.delete(settings)
                session.commit()

        await self.load_settings()
        return rx.toast.success("OpenAI API key removed.")


@rx.page(
    route="/user",
    title="OpenAI Settings",
    on_load=[MainState.init, UserSettingsState.load_settings],
)
@template
def user() -> rx.Component:
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.hstack(
                    rx.icon("key"),
                    rx.heading("OpenAI Settings", size="5"),
                    align="center",
                ),
                rx.text(UserSettingsState.api_key_status, size="3"),
                width="100%",
            ),
            rx.form.root(
                rx.vstack(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("key", size=16, stroke_width=1.5),
                            rx.text("OpenAI API Key"),
                            width="100%",
                            align="center",
                            spacing="2",
                        ),
                        rx.input(
                            placeholder=rx.cond(
                                UserSettingsState.openai_api_key_configured,
                                "Leave blank to keep the saved key",
                                "Enter your OpenAI API key",
                            ),
                            type="password",
                            width="100%",
                            name="openai_api_key",
                        ),
                        direction="column",
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.hstack(
                            rx.icon("box", size=16, stroke_width=1.5),
                            rx.text("OpenAI Model"),
                            width="100%",
                            align="center",
                            spacing="2",
                        ),
                        rx.input(
                            placeholder=DEFAULT_OPENAI_MODEL,
                            value=UserSettingsState.model_input,
                            on_change=UserSettingsState.set_model_input,
                            width="100%",
                            name="openai_model",
                        ),
                        direction="column",
                        spacing="1",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.button(
                            rx.icon("save"),
                            rx.text("Save"),
                            type="submit",
                            width="100%",
                        ),
                        rx.button(
                            rx.icon("trash-2"),
                            rx.text("Remove"),
                            type="button",
                            color_scheme="tomato",
                            variant="outline",
                            on_click=UserSettingsState.clear_openai_api_key,
                        ),
                        width="100%",
                    ),
                    width="100%",
                    spacing="5",
                ),
                on_submit=UserSettingsState.update_openai_settings,
                reset_on_submit=True,
                width="100%",
                max_width="325px",
            ),
            width="100%",
            spacing="4",
            flex_direction=["column", "column", "row"],
        ),
        spacing="6",
        width="100%",
        max_width="800px",
    )
