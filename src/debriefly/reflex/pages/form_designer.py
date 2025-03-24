import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.form_designer.components import (
    form_entry_title,
    form_edit_title,
    field_edit_title,
)
from debriefly.reflex.form_designer.components import (
    FormEditorState,
    FieldEditorState,
    FormSelectState,
)
from debriefly.reflex.form_designer.pages import (
    FormEntryState,
    FormEntryTabState,
    form_editor_page,
    form_entry_page,
    responses_page,
    responses_title,
    responses_analysis_title,
    ResponsesState,
)
from debriefly.reflex.form_designer import routes
from debriefly.reflex.components.chat.chat import chat_ui
from debriefly.reflex.components.chat.state import ChatState
from debriefly.reflex.form_designer import style
from debriefly.reflex.components.analyze.chat import chat_ui as analysis_chat_ui
from debriefly.reflex.components.analyze.state import AnalysisState


@rx.page(
    route=routes.FIELD_EDIT_ID,
    title=field_edit_title(),
    on_load=[MainState.init, FormEditorState.load_form, FieldEditorState.load_field],
)
@template
def _field_edit_id() -> rx.Component:
    return form_editor_page()


@rx.page(
    route=routes.FIELD_EDIT_NEW,
    title=field_edit_title(),
    on_load=[MainState.init, FormEditorState.load_form, FieldEditorState.load_field],
)
@template
def _field_edit_new() -> rx.Component:
    return form_editor_page()


@rx.page(
    route=routes.FORM_EDIT_ID,
    title=form_edit_title(),
    on_load=[MainState.init, FormEditorState.load_form],
)
@template
def _form_edit_id() -> rx.Component:
    return form_editor_page()


@rx.page(
    route=routes.FORM_EDIT_NEW,
    title=form_edit_title(),
    on_load=[MainState.init, FormSelectState.load_forms, FormEditorState.load_form],
)
@template
def _form_edit_new() -> rx.Component:
    return form_editor_page()


@rx.page(
    route=routes.RESPONSES,
    title=responses_title(),
    on_load=[MainState.init, ResponsesState.load_responses],
)
@template
def _responses() -> rx.Component:
    return responses_page()


@rx.page(
    route=routes.RESPONSES_ANALYZE,
    title=responses_analysis_title(),
    on_load=[MainState.init, AnalysisState.on_load],
)
@template
def _responses_analysis() -> rx.Component:
    return analysis_chat_ui()


# ----------------------
# Non-templated pages (no login required; no enclosing layout)
# ----------------------


@rx.page(
    route=routes.FORM_ENTRY,
    title=form_entry_title(),
    on_load=[MainState.init, FormEntryState.load_form, FormEntryTabState.on_load],
)
def _form_entry() -> rx.Component:
    return form_entry_page()


@rx.page(
    route=routes.FORM_ENTRY_CHAT,
    title="FORM_ENTRY_CHAT",
    on_load=[MainState.init, ChatState.on_load],
)
def _form_entry_chat() -> rx.Component:
    return chat_ui()


@rx.page(
    route=routes.FORM_ENTRY_SUCCESS,
    title="FORM_ENTRY_SUCCESS",
    on_load=[MainState.init],
)
def _form_entry_success() -> rx.Component:
    return style.layout(
        rx.cond(
            FormEntryState.form.show_submission_code,
            rx.cond(
                FormEntryState.is_preview,
                rx.card(
                    rx.box(
                        rx.text(
                            "Thank you for your responses. If you need to get paid, you need the following submission code:"
                        ),
                        rx.button(
                            rx.icon("copy"),
                            rx.text("[user id will be shown here]"),
                        ),
                    ),
                    text_align="center",
                ),
                rx.card(
                    rx.box(
                        rx.text(
                            "Thank you for your responses. If you need to get paid, you need the following submission code:"
                        ),
                        rx.button(
                            rx.icon("copy"),
                            FormEntryState.client_token,
                            on_click=lambda: rx.set_clipboard(
                                FormEntryState.client_token
                            ),
                        ),
                    ),
                    text_align="center",
                ),
            ),
            rx.card(
                rx.box(
                    rx.text(
                        "Thank you for your responses. You can now close this browser window."
                    ),
                ),
                text_align="center",
            ),
        ),
        rx.button(
            "Close Survey",
            on_click=rx.call_script("window.close()"),
            color_scheme="green",
            variant="solid",
            padding="0.75em 1.5em",
            font_size="lg",
            _hover={"background_color": "green.600"},
        ),
    )
