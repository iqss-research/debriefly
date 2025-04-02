"""Edit Question modal."""
import reflex as rx
from debriefly.reflex.form_designer import constants, routes, utils
from debriefly.reflex.backend.models import Field, FieldType, Option
from debriefly.reflex.backend.backend import MainState as AppState
from debriefly.reflex.form_designer.components.form_editor import FormEditorState

# from debriefly.reflex.form_designer.components.field_view import field_input
# import uuid
# from debriefly.reflex.backend.models import Form

display_names = {
    "text": "Small Text Area",
    "radio": "Radio Buttons",
    "checkbox": "Checkboxes",
    "textarea": "Large Text Area",
}

tooltips = {
    "question_identifier": "A unique identifier for the question (not shown to users)",
    "question_text": "The text of the question that will be displayed to the survey participants.",
    "answer_format": "The format in which the survey participants will provide their answers.",
    "required": "If checked, the survey participants must answer this question to proceed.",
    "debriefing": "If checked, this question will be used for automated cognitive debriefing purposes.",
    "answer_options": "The list of options for the survey participants to choose from (for radio or checkbox formats).",
    "minimum_time": "The minimum time (in minutes) for survey participants to spend on debriefing (conversation with LLM). After this time, the participants can finish the conversation."
}


class FieldEditorState(AppState):
    """Handle editing of a single field."""

    field: Field = Field(min_debriefing_time=1800)
    form_owner_id: int = -1
    field_editor_open: bool = False

    @rx.var
    def min_debriefing_time_in_minutes(self) -> int:
        """Convert min_debriefing_time from seconds to minutes for display."""
        return (
            self.field.min_debriefing_time // 60
            if self.field.min_debriefing_time is not None
            else 1
        )

    def increment_min_time(self):
        """Increase the minimum debriefing time by 1 minute."""
        current_time = self.field.min_debriefing_time or 0
        self.field.min_debriefing_time = current_time + 60  # Add 1 minute (60 seconds)

    def decrement_min_time(self):
        """Decrease the minimum debriefing time by 1 minute, not below 0."""
        current_time = self.field.min_debriefing_time or 0
        new_time = current_time - 60
        self.field.min_debriefing_time = max(0, new_time)  # Prevent negative values

    def _user_has_access(self):
        return self.form_owner_id == self.user_id

    def handle_submit(self, form_data: dict[str, str]):
        if self.field.type_ == FieldType.static:
            self.field.prompt = form_data["prompt"]
        else:
            self.field.name = form_data["field_name"]
            self.field.type_ = form_data["type_"]
            self.field.required = bool(form_data.get("required"))
            self.field.debriefing = bool(form_data.get("debriefing"))

        self.field_editor_open = False
        return [
            FormEditorState.update_field(self.field),
            rx.redirect(routes.edit_form(self.form_id)),
        ]

    # def handle_required_change(self, is_checked: bool):
    #    self.field.required = is_checked

    # def handle_debriefing_change(self, is_checked: bool):
    #    self.field.debriefing = is_checked

    def handle_modal_open_change(self, is_open: bool):
        self.field_editor_open = is_open
        if not is_open:
            return rx.redirect(routes.edit_form(self.form_id))

    async def load_field(self):
        form_state = await self.get_state(FormEditorState)
        self.form_owner_id = form_state.form.user_id
        if not self._user_has_access():
            return
        if self.field_id == "new":
            self.field = Field(form_id=self.form_id, min_debriefing_time=1800)
        else:
            with rx.session() as session:
                self.field = session.get(Field, self.field_id)
                if self.field.min_debriefing_time is None:
                    self.field.min_debriefing_time = 1800
        self.field_editor_open = True

    def set_type(self, type_: str):
        self.field.type_ = FieldType(type_)

    def set_field(self, key: str, value: str):
        setattr(self.field, key, value)

    def set_option(self, index: int, key: str, value: str):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.add(self.field)
            if self.field.id is None:
                session.commit()
                session.refresh(self.field)
            option = self.field.options[index]
            option.field_id = self.field.id
            setattr(option, key, value)
            session.add(option)
            session.commit()
            session.refresh(self.field)

    def add_option(self):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.add(self.field)
            if not self.field.id:
                session.commit()
                session.refresh(self.field)
            option = Option(field_id=self.field.id)
            self.field.options.append(option)
            session.add(option)
            session.add(self.field)
            session.commit()
            session.refresh(self.field)
            return utils.focus_input_in_class("fd-Option-Label")

    def delete_option(self, index: int):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.add(self.field)
            option_to_delete = session.get(Option, self.field.options[index].id)
            if option_to_delete is not None:
                session.delete(option_to_delete)
            del self.field.options[index]
            session.commit()
            session.refresh(self.field)

    def open_new_static_field(self):
        """Create a new static field and open the editor modal."""
        self.field = Field(form_id=self.form_id)
        self.field.type_ = FieldType.static  # Ensure the type is set to static
        self.field_editor_open = True

    def handle_required_change(self, is_checked: bool):
        """Update the 'Required' field only if 'Debriefing' is not selected."""
        if not self.field.debriefing:
            self.field.required = is_checked

    def handle_debriefing_change(self, is_checked: bool):
        """Update 'Debriefing' and enforce 'Required' when 'Debriefing' is checked."""
        self.field.debriefing = is_checked
        if is_checked:
            self.field.required = True  # Automatically set 'Required' to True


def field_is_enumerated_cond(
    if_enumerated: rx.Component | rx.Var,
) -> rx.Component | rx.Var:
    return rx.cond(
        rx.Var.create(
            [
                FieldType.radio.value,
                FieldType.checkbox.value,
            ]
        ).contains(FieldEditorState.field.type_),
        if_enumerated,
    )


def option_editor(option: Option, index: int):
    return rx.card(
        rx.hstack(
            rx.el.label(
                rx.text("Label"),
                rx.input(
                    placeholder="Label",
                    class_name="fd-Option-Label",
                    value=option.label,
                    on_change=lambda v: FieldEditorState.set_option(index, "label", v),
                ),
            ),
            rx.el.label(
                rx.text("Value"),
                rx.input(
                    placeholder=rx.cond(option.label != "", option.label, "Value"),
                    value=option.value,
                    on_change=lambda v: FieldEditorState.set_option(index, "value", v),
                ),
            ),
            rx.button(
                rx.icon(tag="x"),
                on_click=FieldEditorState.delete_option(index),
                type="button",
                color_scheme="tomato",
            ),
            align="end",
        ),
    )


def field_editor_input(key: str):
    return rx.el.label(
        key.capitalize(),
        rx.input(
            placeholder=key.capitalize(),
            name=f"field_{key}",
            value=getattr(FieldEditorState.field, key),
            on_change=lambda v: FieldEditorState.set_field(key, v),
            width="100%",
        ),
        width="100%",
    )


def field_editor_input_prompt(key: str):
    return rx.el.label(
        key.capitalize(),
        rx.match(
            FieldEditorState.field.type_,
            (
                FieldType.static.value,
                rx.text_area(
                    placeholder=key.capitalize(),
                    name=f"field_{key}",
                    value=getattr(FieldEditorState.field, key),
                    on_change=lambda v: FieldEditorState.set_field(key, v),
                    width="100%",
                ),
            ),
            rx.input(
                placeholder=key.capitalize(),
                name=f"field_{key}",
                value=getattr(FieldEditorState.field, key),
                on_change=lambda v: FieldEditorState.set_field(key, v),
                width="100%",
            ),
        ),
        width="100%",
    )


def field_editor():
    return rx.form(
        rx.hstack(
            # Left column: Question details
            rx.vstack(
                # Question Identifier (formerly Name)
                rx.vstack(
                    rx.hstack(
                        rx.text("Question Identifier", weight="bold"),
                        rx.tooltip(
                            rx.icon("info", size=16),
                            content=tooltips["question_identifier"],
                        ),
                        align="center",
                    ),
                    rx.input(
                        placeholder="Question Identifier",
                        name="field_name",
                        value=FieldEditorState.field.name,
                        on_change=lambda v: FieldEditorState.set_field("name", v),
                        width="100%",
                    ),
                    width="100%",
                ),
                # Question Text (formerly Prompt)
                rx.vstack(
                    rx.hstack(
                        rx.text("Question Text", weight="bold"),
                        rx.tooltip(
                            rx.icon("info", size=16),
                            content=tooltips["question_text"],
                        ),
                        align="center",
                    ),
                    rx.match(
                        FieldEditorState.field.type_,
                        (
                            FieldType.static.value,
                            rx.text_area(
                                placeholder="Question Text",
                                name="field_prompt",
                                value=FieldEditorState.field.prompt,
                                on_change=lambda v: FieldEditorState.set_field(
                                    "prompt", v
                                ),
                                width="100%",
                            ),
                        ),
                        rx.input(
                            placeholder="Question Text",
                            name="field_prompt",
                            value=FieldEditorState.field.prompt,
                            on_change=lambda v: FieldEditorState.set_field("prompt", v),
                            width="100%",
                        ),
                    ),
                    width="100%",
                ),
                # Answer Format (formerly Type)
                rx.vstack(
                    rx.hstack(
                        rx.text("Answer Format", weight="bold"),
                        rx.tooltip(
                            rx.icon("info", size=16),
                            content=tooltips["answer_format"],
                        ),
                        align="center",
                    ),
                    rx.select.root(
                        rx.select.trigger(),
                        rx.select.content(
                            *[
                                rx.select.item(
                                    display_names.get(t.value, t.value), value=t.value
                                )
                                for t in FieldType
                                if t not in [FieldType.static, FieldType.pagebreak]
                            ],
                        ),
                        name="type_",
                        value=FieldEditorState.field.type_.to(str),
                        on_change=FieldEditorState.set_type,
                    ),
                    rx.cond(
                        (FieldEditorState.field.type_ != FieldType.static.value)
                        & (FieldEditorState.field.type_ != FieldType.pagebreak.value),
                        rx.vstack(
                            # Required checkbox with tooltip
                            rx.hstack(
                                rx.checkbox(
                                    "Required",
                                    name="required",
                                    checked=FieldEditorState.field.required,
                                    on_change=FieldEditorState.handle_required_change,
                                ),
                                rx.tooltip(
                                    rx.icon("info", size=16),
                                    content=tooltips["required"],
                                ),
                                rx.cond(
                                    FieldEditorState.field.debriefing,
                                    rx.text(
                                        "(automatically required for debriefing)",
                                        size="1",
                                        color="gray",
                                    ),
                                ),
                                align="center",
                            ),
                            # Debriefing checkbox with tooltip
                            rx.hstack(
                                rx.checkbox(
                                    "Debriefing",
                                    name="debriefing",
                                    checked=FieldEditorState.field.debriefing,
                                    on_change=FieldEditorState.handle_debriefing_change,
                                ),
                                rx.tooltip(
                                    rx.icon("info", size=16),
                                    content=tooltips["debriefing"],
                                ),
                                align="center",
                            ),
                            # Minimum Time input for debriefing
                            rx.cond(
                                FieldEditorState.field.debriefing,
                                rx.hstack(
                                    rx.tooltip(
                                        rx.text("Minimum Time (minutes)"),
                                        content=tooltips["minimum_time"],
                                    ),
                                    rx.button(
                                        "-",
                                        on_click=FieldEditorState.decrement_min_time,
                                        type="button",  # Prevent form submission
                                    ),
                                    rx.text(
                                        FieldEditorState.min_debriefing_time_in_minutes.to_string()
                                    ),
                                    rx.button(
                                        "+",
                                        on_click=FieldEditorState.increment_min_time,
                                        type="button",  # Prevent form submission
                                    ),
                                    spacing="2",
                                ),
                            ),
                        ),
                    ),
                    align="start",
                ),
                width="50%",  # Adjust width as needed
                align="start",
            ),
            # Right column: Answer Options panel for radio and checkbox
            field_is_enumerated_cond(
                rx.vstack(
                    rx.hstack(
                        rx.text("Answer Options", weight="bold"),
                        rx.tooltip(
                            rx.icon("info", size=16),
                            content=tooltips["answer_options"],
                        ),
                        align="center",
                    ),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(FieldEditorState.field.options, option_editor),
                        ),
                        max_height="200px",
                    ),
                    rx.hstack(
                        rx.button(
                            rx.icon("plus", size=16),
                            rx.text("Add Option"),
                            on_click=FieldEditorState.add_option,
                            type="button",
                            variant="outline",
                            size="sm",
                        ),
                        justify="start",
                    ),
                    width="50%",  # Adjust width as needed
                    align="start",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        rx.hstack(
            rx.dialog.close(rx.button("CANCEL")),
            rx.button("SAVE", type="submit"),
            justify="end",
            width="100%",
        ),
        on_submit=FieldEditorState.handle_submit,
    )


def field_editor_modal():
    return rx.dialog.root(
        rx.dialog.content(
            rx.cond(
                FieldEditorState.field.type_ == FieldType.static.value,
                rx.vstack(
                    rx.dialog.title("Edit Plain Text (Markdown)"),
                    static_field_editor(),
                ),
                rx.vstack(
                    rx.dialog.title("Edit Question"),
                    field_editor(),
                ),
            ),
        ),
        open=FieldEditorState.field_editor_open,
        on_open_change=FieldEditorState.handle_modal_open_change,
    )


def field_edit_title():
    form_name = rx.cond(
        rx.State.form_id == "",
        utils.quoted_var("New Survey"),
        rx.cond(
            FormEditorState.form,
            FormEditorState.form.name,
            utils.quoted_var("Unknown Survey"),
        ),
    )
    field_name = rx.cond(
        rx.State.field_id == "",
        utils.quoted_var("New Field"),
        rx.cond(
            FieldEditorState.field,
            FieldEditorState.field.name,
            utils.quoted_var("Unknown Field"),
        ),
    )
    return f"{constants.TITLE} | {form_name} | {field_name}"


def static_field_editor():
    return rx.form(
        rx.input(
            type="hidden",
            name="prompt",
            value=FieldEditorState.field.prompt,
            style={"display": "none"},
        ),
        rx.vstack(
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Edit", value="edit"),
                    rx.tabs.trigger("Preview", value="preview"),
                ),
                rx.tabs.content(
                    rx.text_area(
                        name="prompt",
                        placeholder="Your text content...",
                        value=FieldEditorState.field.prompt,
                        on_change=lambda v: FieldEditorState.set_field("prompt", v),
                        width="100%",
                        min_height="200px",
                        resize="vertical",
                    ),
                    value="edit",
                ),
                rx.tabs.content(
                    rx.markdown(FieldEditorState.field.prompt),
                    value="preview",
                ),
                default_value="edit",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(rx.button("CANCEL")),
                rx.button("SAVE", type="submit"),
            ),
        ),
        on_submit=FieldEditorState.handle_submit,
    )
