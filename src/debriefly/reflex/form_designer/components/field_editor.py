"""Edit Question modal."""
import reflex as rx
from pathlib import Path
from debriefly.reflex.form_designer import constants, routes, utils
from debriefly.reflex.backend.models import Field, FieldType, Option
from debriefly.reflex.backend.backend import MainState as AppState
from debriefly.reflex.form_designer.components.form_editor import FormEditorState
from debriefly.openai import check_prompt_compliance, PromptVerdict

# from debriefly.reflex.form_designer.components.field_view import field_input
# import uuid
# from debriefly.reflex.backend.models import Form


display_names = {
    "text": "Small Text Area",
    "radio": "Radio Buttons",
    "checkbox": "Checkboxes",
    "textarea": "Large Text Area",
    "scale": "Scale (slider)",
}

tooltips = {
    "question_identifier": "A unique identifier for the question (not shown to users)",
    "question_text": "The text of the question that will be displayed to the survey participants.",
    "answer_format": "The format in which the survey participants will provide their answers.",
    "required": "If checked, the survey participants must answer this question to proceed.",
    "debriefing": "If checked, this question will be used for automated cognitive debriefing purposes.",
    "answer_options": "The list of options for the survey participants to choose from (for radio or checkbox formats).",
    "minimum_time": "The minimum time (in minutes) for survey participants to spend on debriefing (conversation with LLM). After this time, the participants can finish the conversation.",
    "maximum_time": "The maximum time (in minutes) for survey participants to spend on debriefing (conversation with LLM). After this time, the conversation will be ended automatically.",
    "system_prompt": "Edit the system prompt that governs the LLM behavior (Caution: you must check if your prompt works well in your context).",
    "system_prompt_edit": "Edit the system prompt that governs the LLM behavior. You must include the instruction about {{end_of_survey_token}}, which is the token that indicates the end of the survey. You are NOT allowed to create system prompts that are not for the cognitive debriefing.",
    "initial_message_edit": "Edit the initial message that the assistant will send to the user at first. You must include the token {{question}}, which is the token that will be replaced by the question text.",
}


class FieldEditorState(AppState):
    """Handle editing of a single field."""

    field: Field = Field(
        min_debriefing_time=1800, max_debriefing_time=3600
    )  # Default to 30 minutes for min and 60 for max
    form_owner_id: int = -1
    field_editor_open: bool = False

    show_prompt_editor: bool = False  # NEW flag
    default_system_message: str = ""
    default_initial_message: str = ""

    error: str = ""

    def toggle_prompt_editor(self):
        self.show_prompt_editor = not self.show_prompt_editor

    def update_scale_min(self, v: str):
        """Store the *current* slider minimum as an int (or clear if blank)."""
        self.field.scale_min = int(v) if v else None

    def update_scale_max(self, v: str):
        """Store the *current* slider maximum as an int (or clear if blank)."""
        self.field.scale_max = int(v) if v else None

    @rx.var
    def min_debriefing_time_in_minutes(self) -> int:
        """Convert min_debriefing_time from seconds to minutes for display."""
        return (
            self.field.min_debriefing_time // 60
            if self.field.min_debriefing_time is not None
            else 1
        )

    @rx.var
    def max_debriefing_time_in_minutes(self) -> int:
        return (
            self.field.max_debriefing_time // 60
            if self.field.max_debriefing_time is not None
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

    def increment_max_time(self):
        """Increase the maximum debriefing time by 1 minute."""
        current_time = self.field.max_debriefing_time or 0
        self.field.max_debriefing_time = current_time + 60  # Add 1 minute (60 seconds)

    def decrement_max_time(self):
        """Decrease the minimum debriefing time by 1 minute, not below 0."""
        current_time = self.field.max_debriefing_time or 0
        new_time = current_time - 60
        self.field.max_debriefing_time = max(0, new_time)  # Prevent negative values

    def _user_has_access(self):
        return self.form_owner_id == self.user_id

    def handle_submit(self, form_data: dict[str, str]):
        # validating missingness
        missing: list[str] = []

        # 1. question wording (prompt)
        if not form_data.get("field_prompt", "").strip():
            missing.append("Question Text")

        # 2. identifier (name)
        if not form_data.get("field_name", "").strip():
            missing.append("Question Identifier")

        # 3. answer options when the answer type needs them
        needs_options = form_data.get("type_") in {
            FieldType.radio.value,
            FieldType.checkbox.value,
        }
        if needs_options and not any(opt.label.strip() for opt in self.field.options):
            missing.append("Answer Options")

        if form_data.get("type_") == FieldType.scale.value:
            min_val = self.field.scale_min
            max_val = self.field.scale_max
            if min_val is None or max_val is None:
                missing.append("Scale Range")
            elif min_val >= max_val:
                self.error = "Scale minimum must be **less** than maximum."
                return

        if missing:
            # show a single, clear message and abort the save
            self.error = f"The required field is not filled ({', '.join(missing)})."
            return  # stay in the editor
            # return toast.error(
            #    f"The required field is not filled ({', '.join(missing)}).",
            #    style={"z-index": 2000},
            # )

        self.error = ""  # clear the error message

        # check system prompt
        sys_prompt = form_data.get("custom_system_message", "").strip()
        init_msg = form_data.get("custom_initial_message", "").strip()

        # run compliance checks (only on non-empty edits) only if debriefing is checked
        if self.field.debriefing:
            for which, txt in {
                "system prompt": sys_prompt,
                "initial message": init_msg,
            }.items():
                if not txt:
                    continue

                verdict = check_prompt_compliance(
                    txt,
                    api_key=self.config["AZURE_OPENAI_API_KEY"],
                    api_version=self.config["AZURE_OPENAI_API_VERSION"],
                    api_endpoint=self.config["AZURE_OPENAI_ENDPOINT"],
                    api_model=self.config["AZURE_OPENAI_DEPLOYMENT_MODEL"],
                )

                if verdict == PromptVerdict.REJECT:
                    self.error = f"{which.title()} rejected. Your prompt must be about cognitive debriefing."
                    return  # abort save, stay in modal

        if self.field.type_ == FieldType.static:
            self.field.prompt = form_data["prompt"]
        else:
            self.field.name = form_data["field_name"]
            self.field.type_ = form_data["type_"]
            self.field.required = bool(form_data.get("required"))
            self.field.debriefing = bool(form_data.get("debriefing"))

        if "custom_system_message" in form_data:
            self.field.custom_system_message = form_data[
                "custom_system_message"
            ].strip()

        if "custom_initial_message" in form_data:
            self.field.custom_initial_message = form_data[
                "custom_initial_message"
            ].strip()

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
        self.show_prompt_editor = False
        self.error = ""
        if self.field_id == "new":
            self.field = Field(
                form_id=self.form_id, min_debriefing_time=1800, max_debriefing_time=3600
            )  # Default to 30 minutes for min and 60 for max
        else:
            with rx.session() as session:
                self.field = session.get(Field, self.field_id)
                if self.field.min_debriefing_time is None:
                    self.field.min_debriefing_time = 1800
                if self.field.max_debriefing_time is None:
                    self.field.max_debriefing_time = 3600
        self.field_editor_open = True

        # --------- load default templates on first run -------
        if not self.default_system_message:
            tmpl_dir = Path(__file__).resolve().parents[3]
            self.default_system_message = (
                tmpl_dir / "data/templates/system_message.jinja"
            ).read_text()
            self.default_initial_message = (
                tmpl_dir / "data/templates/initial_message.jinja"
            ).read_text()

    @rx.var
    def system_prompt_value(self) -> str:

        return (
            self.field.custom_system_message
            if (self.field.custom_system_message or "").strip()
            else self.default_system_message
        )

    @rx.var
    def initial_prompt_value(self) -> str:
        return (
            self.field.custom_initial_message
            if (self.field.custom_initial_message or "").strip()
            else self.default_initial_message
        )

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

    def reset_system_prompt(self):
        """Clear the override so the default template shows again."""
        self.set_field("custom_system_message", self.default_system_message)

    def reset_initial_prompt(self):
        """Clear the override so the default template shows again."""
        self.set_field("custom_initial_message", self.default_initial_message)


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


def field_is_scale_cond(content: rx.Component) -> rx.Component:
    return rx.cond(
        FieldEditorState.field.type_ == FieldType.scale.value,
        content,
        rx.fragment(),  # nothing if not scale
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
    def third_or_half() -> rx.Var[str]:
        """Return '33%' when the prompt-editor is visible, else '50%'."""
        return rx.cond(FieldEditorState.show_prompt_editor, "33%", "50%")

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
                        rx.text_area(
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
                                rx.cond(
                                    FieldEditorState.field.debriefing,
                                    rx.button(
                                        "Edit System Prompts",
                                        on_click=FieldEditorState.toggle_prompt_editor,
                                        type="button",
                                        variant="outline",
                                        color_scheme="green",
                                    ),
                                ),
                                rx.cond(
                                    FieldEditorState.field.debriefing,
                                    rx.tooltip(
                                        rx.icon("info", size=16),
                                        content=tooltips["system_prompt"],
                                    ),
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
                            rx.cond(
                                FieldEditorState.field.debriefing,
                                rx.hstack(
                                    rx.tooltip(
                                        rx.text("Maximum Time (minutes)"),
                                        content=tooltips["maximum_time"],
                                    ),
                                    rx.button(
                                        "-",
                                        on_click=FieldEditorState.decrement_max_time,
                                        type="button",  # Prevent form submission
                                    ),
                                    rx.text(
                                        FieldEditorState.max_debriefing_time_in_minutes.to_string()
                                    ),
                                    rx.button(
                                        "+",
                                        on_click=FieldEditorState.increment_max_time,
                                        type="button",  # Prevent form submission
                                    ),
                                    spacing="2",
                                ),
                            ),
                        ),
                    ),
                    align="start",
                ),
                width=third_or_half(),  # Adjust width as needed
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
                    width=third_or_half(),  # Adjust width as needed
                    align="start",
                ),
            ),
            field_is_scale_cond(
                rx.vstack(
                    rx.hstack(
                        rx.text("Scale Range", weight="bold"),
                        rx.tooltip(
                            rx.icon("info", size=16),
                            content="Choose the lowest and highest numbers the slider can take.",
                        ),
                        align="center",
                    ),
                    rx.hstack(
                        rx.vstack(
                            rx.text("Minimum", size="sm"),
                            rx.input(
                                type="number",
                                value=FieldEditorState.field.scale_min.to(str),
                                on_change=FieldEditorState.update_scale_min,
                                width="6em",
                            ),
                        ),
                        rx.vstack(
                            rx.text("Maximum", size="sm"),
                            rx.input(
                                type="number",
                                value=FieldEditorState.field.scale_max.to(str),
                                on_change=FieldEditorState.update_scale_max,
                                width="6em",
                            ),
                        ),
                        spacing="4",
                    ),
                    width=third_or_half(),
                    align="start",
                ),
            ),
            rx.cond(
                FieldEditorState.show_prompt_editor,
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.text("System prompt", weight="bold"),
                            rx.button(
                                "Reset",
                                on_click=FieldEditorState.reset_system_prompt,
                                variant="outline",
                                size="2",
                                type="button",
                            ),
                            rx.tooltip(
                                rx.icon("info", size=16),
                                content=tooltips["system_prompt_edit"],
                            ),
                        ),
                        rx.text_area(
                            name="custom_system_message",
                            placeholder="Fill the system prompt that governs the LLM behavior",
                            value=FieldEditorState.system_prompt_value,
                            on_change=lambda v: FieldEditorState.set_field(
                                "custom_system_message", v
                            ),
                            rows="6",
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text("Initial assistant message", weight="bold", mt="3"),
                            rx.button(
                                "Reset",
                                on_click=FieldEditorState.reset_initial_prompt,
                                variant="outline",
                                size="2",
                                type="button",
                            ),
                            rx.tooltip(
                                rx.icon("info", size=16),
                                content=tooltips["initial_message_edit"],
                            ),
                        ),
                        rx.text_area(
                            name="custom_initial_message",
                            placeholder="Fill the initial message that the assistant will send to the user at first",
                            value=FieldEditorState.initial_prompt_value,
                            on_change=lambda v: FieldEditorState.set_field(
                                "custom_initial_message", v
                            ),
                            rows="4",
                            width="100%",
                        ),
                        rx.markdown(
                            """
                            Please use the following special tokens:
                            - **{{ question }}**: This will be replaced by the question text.
                            - **{{ response }}**: This will be replaced by the user response to the question.
                            - **{{ end_of_survey_token }}**: This must be generated by the LLM to finish.
                            """,
                            custom_styles={
                                "ol": {
                                    "margin_top": "0.3em",
                                },
                            },
                        ),
                        spacing="2",
                    ),
                    bg=rx.color("gray", 2),
                    p="3",
                    border_radius="md",
                    width="33%",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        rx.hstack(
            rx.cond(
                FieldEditorState.error,
                rx.text(
                    FieldEditorState.error,
                    color="red",
                    font_size="sm",
                    font_weight="bold",
                ),
            ),
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
            style={
                "width": "90vw",  # responsive
                "maxWidth": "72rem",  # ≈ 6xl   raise or lower as you like
            },
            p="4",
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


class PromptEditorState(rx.State):
    system_prompt: str = ""  # what you store in DB
    initial_message: str = ""
    editor_open: bool = False  # modal visibility

    # -------- event handlers --------
    def open_editor(self):
        """Open the edit modal."""
        self.editor_open = True  # returning None is fine here

    def close_editor(self):
        self.editor_open = False

    def save(self, form_data: dict[str, str]):
        """Persist both text areas and close the modal."""
        self.system_prompt = form_data["system_prompt"]
        self.initial_message = form_data["initial_message"]
        self.editor_open = False
        with rx.session() as session:  # SQL save
            session.add(self)  # or your own table/model
            session.commit()


def prompt_editor_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.form(
                rx.vstack(
                    rx.text_area(
                        name="system_prompt",
                        placeholder="System prompt …",
                        value=PromptEditorState.system_prompt,
                        width="100%",
                        rows=8,
                    ),
                    rx.text_area(
                        name="initial_message",
                        placeholder="Assistant’s first reply …",
                        value=PromptEditorState.initial_message,
                        width="100%",
                        rows=5,
                    ),
                    rx.hstack(
                        rx.dialog.close(rx.button("Cancel")),
                        rx.button("Save", type="submit"),
                        justify="end",
                    ),
                ),
                on_submit=PromptEditorState.save,
            ),
        ),
        open=PromptEditorState.editor_open,
        on_open_change=PromptEditorState.set_editor_open,  # built-in setter
    )
