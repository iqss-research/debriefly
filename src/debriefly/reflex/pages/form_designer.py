import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.form_designer.components import form_edit_title, field_edit_title
from debriefly.reflex.form_designer.components import (
    FormEditorState,
    FieldEditorState,
    FormSelectState,
)
from debriefly.reflex.form_designer.pages import (
    FormEntryState,
    form_editor_page,
    form_entry_page,
    responses_page,
    responses_title,
    ResponsesState,
)
from debriefly.reflex.form_designer import routes
from debriefly.reflex.components.chat.chat import chat_ui
from debriefly.reflex.components.chat.state import ChatState


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
    route=routes.FORM_ENTRY,
    title="TODO",
    on_load=[MainState.init, FormEntryState.load_form],
)
def _form_entry() -> rx.Component:
    return form_entry_page()


@rx.page(
    route=routes.FORM_ENTRY_SUCCESS,
    title="Form Response Saved",
    on_load=[MainState.init, ChatState.on_load],
)
def _form_entry_success() -> rx.Component:
    # return form_entry_success()
    return chat_ui()


@rx.page(
    route=routes.RESPONSES,
    title=responses_title(),
    on_load=[MainState.init, ResponsesState.load_responses],
)
@template
def _responses() -> rx.Component:
    return responses_page()
