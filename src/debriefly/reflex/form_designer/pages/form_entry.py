import itertools
import reflex as rx
from sqlmodel import select
from debriefly.reflex.form_designer import routes, style
from debriefly.reflex.form_designer.components import field_view
from debriefly.reflex.backend.models import FieldType, Field, FieldValue, Form, Response

Missing = object()


class FormEntryState(rx.State):
    form: Form = Form()
    client_token: str = rx.Cookie("")

    def _ensure_client_token(self):
        if self.client_token == "":
            self.client_token = self.router.session.client_token
        return self.client_token

    def load_form(self):
        if self.form_id != "":
            self.load_form_by_id(self.form_id)
        else:
            self.form = Form()

    def load_form_by_id(self, id_: int):
        with rx.session() as session:
            self.form = session.get(Form, id_)

    def handle_submit(self, form_data):
        with rx.session() as session:
            response = session.exec(
                select(Response)
                .where(Response.client_token == self._ensure_client_token())
                .where(Response.form_id == self.form.id)
            ).first()
            if response is None:
                response = Response(
                    client_token=self._ensure_client_token(), form_id=self.form.id
                )
            for field in self.form.fields:
                value = form_data.get(field.name, Missing)
                if value is not Missing:
                    response.field_values.append(
                        FieldValue(
                            field_id=field.id,
                            value=value,
                        )
                    )
                elif field.type_ == FieldType.checkbox:
                    for option in field.options:
                        key = f"{field.name}___{option.value or option.label or option.id}"
                        value = form_data.get(key, Missing)
                        if value is not Missing:
                            response.field_values.append(
                                FieldValue(field_id=field.id, value=form_data[key])
                            )
                session.add(response)
                session.commit()

        if "done" in form_data:
            return rx.redirect(routes.FORM_ENTRY_SUCCESS)


class FormEntryTabState(rx.State):
    fields: list[list[Field]] = [[]]
    n_tabs: int
    active_tab: int = 0
    is_last_tab: bool = False

    async def on_load(self):
        state = await self.get_state(FormEntryState)
        form = state.form
        if form is not None:
            self.fields = [
                list(group)
                for key, group in itertools.groupby(
                    form.fields, key=lambda field: field.type_ == FieldType.pagebreak
                )
                if not key
            ]
            self.n_tabs = len(self.fields)

    async def advance(self):
        if self.active_tab < self.n_tabs - 1:
            self.active_tab += 1
        self.is_last_tab = self.active_tab == self.n_tabs - 1


def form_entry_tab(fields: list[Field], i: int):
    return rx.tabs.content(
        rx.vstack(rx.foreach(fields, field_view)),
        value=f"tab_{i}",
    )


def form_entry_page():
    return style.layout(
        rx.form(
            rx.vstack(
                rx.center(rx.heading(FormEntryState.form.name)),
                rx.tabs.root(
                    rx.tabs.list(
                        rx.foreach(
                            FormEntryTabState.fields,
                            lambda _, i: rx.tabs.trigger(f"Tab {i}", value=f"tab_{i}"),
                        ),
                        display="none",
                    ),
                    rx.foreach(
                        FormEntryTabState.fields,
                        lambda fields, i: form_entry_tab(fields, i),
                    ),
                    value=f"tab_{FormEntryTabState.active_tab}",
                ),
                rx.cond(
                    FormEntryTabState.is_last_tab,
                    rx.button(
                        "Submit", type="submit", on_click=FormEntryTabState.advance
                    ),
                    rx.button(
                        "Next", type="submit", on_click=FormEntryTabState.advance
                    ),
                ),
            ),
            rx.cond(
                FormEntryTabState.is_last_tab, rx.el.input(type="hidden", name="done")
            ),
            on_submit=FormEntryState.handle_submit,
        ),
    )


def form_entry_success():
    return style.layout(
        rx.heading(f"Your response to form {FormEntryState.form.id} has been saved!"),
    )
