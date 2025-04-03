import reflex as rx
from debriefly.reflex.form_designer import routes
from debriefly.reflex.backend.models import Form
from debriefly.reflex.backend.backend import MainState as AppState


class FormSelectState(AppState):
    forms: list[Form] = []

    def load_forms(self):
        if not self.user_id:  # Wait for user_id to be available
            return
        with rx.session() as session:
            query = Form.select()
            query = query.where(Form.user_id == self.user_id)
            self.forms = list(session.exec(query).all())

    def on_select_change(self, value: str):
        if value == "":
            return rx.redirect(routes.FORM_EDIT_NEW)
        return rx.redirect(routes.edit_form(value))


def form_name(form: Form):
    return form.name


def form_select():
    return rx.box(
        rx.select.root(
            rx.select.trigger(placeholder="Select Survey", width="100%"),
            rx.select.content(
                rx.foreach(
                    FormSelectState.forms,
                    lambda form: rx.select.item(
                        form_name(form), value=form.id.to_string()
                    ),
                ),
            ),
            value=rx.State.form_id,
            on_change=FormSelectState.on_select_change,
            on_mount=FormSelectState.load_forms,
        ),
        width="100%",
    )
