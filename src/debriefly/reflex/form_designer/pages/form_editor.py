import reflex as rx
from debriefly.reflex.form_designer import routes, style
from debriefly.reflex.form_designer.components import (
    # form_select,
    form_editor,
    field_editor_modal,
    FormEditorState,
    FieldEditorState,
)
from debriefly.reflex.backend.models import FieldType


def form_editor_page() -> rx.Component:
    return style.layout(
        form_editor(),
        rx.cond(
            rx.State.form_id != "",
            rx.fragment(
                rx.hstack(
                    rx.tooltip(
                        rx.button(
                            "Add Question",
                            on_click=rx.redirect(
                                routes.edit_field(rx.State.form_id, "new")
                            ),
                            is_disabled=rx.State.form_id == "",
                            type="button",
                        ),
                        content="Add a new question to the survey form",
                    ),
                    rx.tooltip(
                        rx.button(
                            "Add Page Break",
                            on_click=lambda: FormEditorState.add_special_field(
                                FieldType.pagebreak.value
                            ),
                            is_disabled=rx.State.form_id == "",
                            type="button",
                            color_scheme="green",
                        ),
                        content="Add a page break to the survey form. The page break will treat the next question in the new page.",
                    ),
                    rx.tooltip(
                        rx.button(
                            "Add Plain Text",
                            on_click=FieldEditorState.open_new_static_field,
                            is_disabled=rx.State.form_id == "",
                            type="button",
                            color_scheme="purple",
                        ),
                        content="Add a markdown text without answer options. Useful to display instructions or information.",
                    ),
                    rx.tooltip(
                        rx.checkbox(
                            "Show Submission Code Page",
                            checked=FormEditorState.show_submission_code,
                            on_change=FormEditorState.set_show_submission_code,
                        ),
                        content="Show the submission code page at last. The submission code is useful to merge data with other sources (e.g., MTurk).",
                    ),
                    spacing="2",
                ),
                field_editor_modal(),
            ),
        ),
    )
