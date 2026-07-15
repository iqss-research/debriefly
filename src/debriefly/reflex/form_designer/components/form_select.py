import reflex as rx
from debriefly.reflex.form_designer import routes
from debriefly.reflex.backend.models import Form
from debriefly.reflex.backend.backend import MainState
from sqlmodel import select


class FormSelectOption(rx.Base):
    form_id: str
    name: str


class FormSelectState(MainState):
    forms: list[FormSelectOption] = []
    forms_loading: bool = False
    forms_loaded_for_user_id: str = ""

    async def load_forms(self):
        if self.forms_loading:
            return

        if not await self.sync_user_from_session():
            return

        if self.forms_loaded_for_user_id == self.user_id:
            return

        self.forms_loading = True
        yield

        try:
            with rx.session() as s:
                rows = s.exec(
                    select(Form.id, Form.name).where(Form.user_id == self.user_id)
                )
                self.forms = [
                    FormSelectOption(form_id=str(form_id), name=name)
                    for form_id, name in rows
                ]
                self.forms_loaded_for_user_id = self.user_id
        finally:
            self.forms_loading = False

    def refresh_forms(self):
        self.forms_loaded_for_user_id = ""
        yield FormSelectState.load_forms

    def on_select_change(self, value: str):
        if value == "__loading":
            return
        if value == "":
            return rx.redirect(routes.FORM_EDIT_NEW)
        return rx.redirect(routes.edit_form(value))


def form_name(form: FormSelectOption):
    return form.name


def form_select():
    return rx.box(
        rx.select.root(
            rx.select.trigger(
                placeholder=rx.cond(
                    FormSelectState.forms_loading,
                    "Loading surveys...",
                    "Select Survey",
                ),
                width="100%",
            ),
            rx.select.content(
                rx.cond(
                    FormSelectState.forms_loading,
                    rx.select.item("Loading surveys...", value="__loading"),
                    rx.foreach(
                        FormSelectState.forms,
                        lambda form: rx.select.item(
                            form_name(form), value=form.form_id
                        ),
                    ),
                ),
            ),
            value=rx.State.form_id,
            on_change=FormSelectState.on_select_change,
            on_mount=FormSelectState.load_forms,
        ),
        width="100%",
    )
