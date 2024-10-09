import reflex as rx
from debriefly.reflex.form_designer import routes, style
from debriefly.reflex.form_designer.components import (
    form_select,
    form_editor,
    field_editor_modal,
)


def form_editor_page() -> rx.Component:
    return style.layout(
        rx.hstack(
            form_select(),
            rx.button(
                "New Survey",
                on_click=rx.redirect(routes.FORM_EDIT_NEW),
                type="button",
            ),
        ),
        rx.divider(),
        form_editor(),
        rx.cond(
            rx.State.form_id != "",
            rx.fragment(
                rx.button(
                    "Add Question",
                    on_click=rx.redirect(routes.edit_field(rx.State.form_id, "new")),
                    is_disabled=rx.State.form_id == "",
                    type="button",
                ),
                field_editor_modal(),
            ),
        ),
    )
