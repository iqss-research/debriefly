import uuid
import reflex as rx
from debriefly.reflex.form_designer import constants, routes, utils
from debriefly.reflex.backend.backend import MainState as AppState
from debriefly.reflex.form_designer.components.field_view import (
    field_input,
    field_prompt,
)
from debriefly.reflex.backend.models import FieldType, Field, Form, Option
from debriefly.reflex.form_designer.components.form_select import FormSelectState


class FormEditorState(AppState):
    form: Form = Form()
    temp_name: str = ""
    show_submission_code: bool = False

    def _new_form(self):
        return Form(user_id=self.user_id, code=uuid.uuid4().hex)

    def load_form(self):
        if self.form_id != "":
            self.load_form_by_id(self.form_id)
        else:
            self.form = self._new_form()
        self.temp_name = self.form.name

    def load_form_by_id(self, id_: int):
        with rx.session() as session:
            form = session.get(Form, id_)
            if not self._user_has_access(form) or form is None:
                self.form = self._new_form()
                return
            self.form = form
            self.temp_name = self.form.name
            self.show_submission_code = self.form.show_submission_code

    def delete_form(self):
        if self.form.id is not None:
            if not self._user_has_access():
                return
            with rx.session() as session:
                session.delete(session.get(Form, self.form.id))
                session.commit()
                yield rx.redirect(routes.FORM_EDIT_NEW)

    def set_name(self, name: str):
        if not self._user_has_access():
            return
        with rx.session() as session:
            self.form.name = name
            session.add(self.form)
            session.commit()
            session.refresh(self.form)
            yield FormSelectState.load_forms
            if self.form.id > 0:
                return rx.redirect(routes.edit_form(self.form.id))

    def update_field(self, field: Field):
        if not self._user_has_access():
            return
        field.pop("options", None)  # Remove options, relationship
        field = Field(**field)
        with rx.session() as session:
            session.add(self.form)
            session.commit()
            if field.id is None:
                # Assign the next ordering value for new fields
                if self.form.fields:
                    max_ordering = max(f.ordering for f in self.form.fields)
                    field.ordering = max_ordering + 1
                else:
                    field.ordering = 1.0
                self.form.fields.append(field)
                session.add(field)
                session.add(self.form)
                session.commit()
            else:
                for existing_field in self.form.fields:
                    if existing_field.id == field.id:
                        existing_field.name = field.name
                        existing_field.type_ = field.type_
                        existing_field.required = field.required
                        existing_field.debriefing = field.debriefing
                        existing_field.prompt = field.prompt
                        existing_field.custom_system_message = (
                            field.custom_system_message
                        )
                        existing_field.custom_initial_message = (
                            field.custom_initial_message
                        )
                        existing_field.ordering = field.ordering
                        existing_field.min_debriefing_time = field.min_debriefing_time
                        existing_field.max_debriefing_time = field.max_debriefing_time
                        existing_field.scale_min = field.scale_min
                        existing_field.scale_max = field.scale_max
                        session.add(existing_field)
                        session.commit()
            return FormEditorState.load_form_by_id(self.form.id)

    def delete_field(self, field_id):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.delete(session.get(Field, field_id))
            session.commit()
            return FormEditorState.load_form_by_id(self.form.id)

    def add_special_field(self, field_type: str):
        """Add a special field (page break) directly without using the editor."""
        if not self._user_has_access():
            return

        from debriefly.reflex.backend.models import Field, FieldType

        with rx.session() as session:
            session.add(self.form)
            session.commit()

            # Create the new field with default values
            new_field = Field(
                name=f"{'Page Break'} {len(self.form.fields) + 1}",
                type_=FieldType(field_type),
                prompt="",
                form_id=self.form.id,
                ordering=len(self.form.fields) + 1,
            )

            self.form.fields.append(new_field)
            session.add(new_field)
            session.commit()

            return FormEditorState.load_form_by_id(self.form.id)

    def move_field_up(self, field_id: int):
        """Move a field up in the ordering."""
        if not self._user_has_access():
            return

        with rx.session() as session:
            # Get fields sorted by ordering
            fields = sorted(self.form.fields, key=lambda f: f.ordering)

            # Find the field to move and its index
            field_index = next(
                (i for i, f in enumerate(fields) if f.id == field_id), None
            )
            if field_index is None or field_index == 0:
                return  # Field not found or already at the top

            # Swap ordering with the field above it
            current_field = fields[field_index]
            prev_field = fields[field_index - 1]

            # Swap their ordering values
            temp_ordering = current_field.ordering
            current_field.ordering = prev_field.ordering
            prev_field.ordering = temp_ordering

            session.add(current_field)
            session.add(prev_field)
            session.commit()

            return self.load_form_by_id(self.form.id)

    def move_field_down(self, field_id: int):
        """Move a field down in the ordering."""
        if not self._user_has_access():
            return

        with rx.session() as session:
            # Get fields sorted by ordering
            fields = sorted(self.form.fields, key=lambda f: f.ordering)

            # Find the field to move and its index
            field_index = next(
                (i for i, f in enumerate(fields) if f.id == field_id), None
            )
            if field_index is None or field_index == len(fields) - 1:
                return  # Field not found or already at the bottom

            # Swap ordering with the field below it
            current_field = fields[field_index]
            next_field = fields[field_index + 1]

            # Swap their ordering values
            temp_ordering = current_field.ordering
            current_field.ordering = next_field.ordering
            next_field.ordering = temp_ordering

            session.add(current_field)
            session.add(next_field)
            session.commit()

            return self.load_form_by_id(self.form.id)

    async def create_new_survey(self, name: str):
        """Create a new survey with the given name and redirect to its edit page."""
        if not self._user_has_access():
            return
        with rx.session() as session:
            new_form = Form(name=name, user_id=self.user_id, code=uuid.uuid4().hex)
            session.add(new_form)
            session.commit()
            session.refresh(new_form)
            self.form = new_form
            yield rx.redirect(routes.edit_form(new_form.id))

    async def copy_survey(self):
        if not self._user_has_access():
            yield rx.toast.error("You do not have permission to copy this survey.")
            return

        with rx.session() as session:
            # Retrieve the current form
            original_form = session.get(Form, self.form_id)
            if original_form is None:
                yield rx.toast.error("Survey not found.")
                return

            # Create a new form with the same fields and a new name
            new_form = Form(
                name=f"{original_form.name}_copy",
                user_id=self.user_id,
                code=uuid.uuid4().hex,
            )
            session.add(new_form)
            session.commit()  # Commit to assign new_form.id
            session.refresh(new_form)

            # Copy fields from the original form
            for field in original_form.fields:
                new_field = Field(
                    name=field.name,
                    type_=field.type_,
                    required=field.required,
                    debriefing=field.debriefing,
                    min_debriefing_time=field.min_debriefing_time,
                    max_debriefing_time=field.max_debriefing_time,
                    prompt=field.prompt,
                    ordering=field.ordering,
                    form_id=new_form.id,
                )
                session.add(new_field)
                session.flush()  # Flush to assign new_field.id before creating options

                # Copy options if the field has any
                for option in field.options:
                    new_option = Option(
                        label=option.label,
                        value=option.value,
                        field_id=new_field.id,  # new_field.id is now set
                    )
                    session.add(new_option)

            session.commit()  # Commit all changes at once

            # Refresh the sidebar's survey list
            yield FormSelectState.load_forms

            # Redirect to the new survey's editing page
            yield rx.redirect(routes.edit_form(new_form.id))

    def set_show_submission_code(self, value: bool):
        """Update the show_submission_code state and the form in the database."""
        with rx.session() as session:
            self.form.show_submission_code = value
            session.add(self.form)
            session.commit()
            session.refresh(self.form)
            self.show_submission_code = value  # Sync the state variable


def field_edit_view(field: Field):
    return rx.card(
        rx.hstack(
            # Conditional rendering for field prompt
            rx.cond(
                field.type_ == FieldType.pagebreak.value,
                field_prompt(field, show_name=True),
                rx.link(
                    field_prompt(field, show_name=True),
                    href=routes.edit_field(FormEditorState.form.id, field.id),
                ),
            ),
            # Use a box with margin_left="auto" to push buttons to the right
            rx.box(
                rx.hstack(
                    rx.tooltip(
                        rx.button(
                            "↑",
                            on_click=lambda: FormEditorState.move_field_up(field.id),
                            variant="outline",
                            size="xs",
                            border_radius="md",
                            width="30px",
                            height="30px",
                            padding="0",
                            background_color="white",
                            _hover={"background_color": "blue.50"},
                        ),
                        content="Move Up",
                    ),
                    rx.tooltip(
                        rx.button(
                            "↓",
                            on_click=lambda: FormEditorState.move_field_down(field.id),
                            variant="outline",
                            size="xs",
                            border_radius="md",
                            width="30px",
                            height="30px",
                            padding="0",
                            background_color="white",
                            _hover={"background_color": "blue.50"},
                        ),
                        content="Move Down",
                    ),
                    rx.tooltip(
                        rx.button(
                            "×",
                            on_click=lambda: FormEditorState.delete_field(field.id),
                            variant="outline",
                            size="xs",
                            border_radius="md",
                            width="30px",
                            height="30px",
                            padding="0",
                            color="red.500",
                            background_color="white",
                            _hover={"background_color": "red.50"},
                        ),
                        content="Delete Question",
                    ),
                    spacing="1",
                ),
                margin_left="auto",
            ),
            width="100%",  # Ensure the hstack spans the full width
            margin_bottom="12px",
        ),
        rx.hstack(
            rx.hstack(
                field_input(field, editing=True),
                flex_wrap="wrap",
            ),
            rx.text(rx.cond(field.required, "(required)", ""), size="1", ml="3"),
            rx.text(rx.cond(field.debriefing, "(debriefing)", ""), size="1", ml="3"),
            justify="between",
        ),
    )


def get_resolved_url(form_code: str) -> str:
    return f"{AppState.base_url}{routes.show_form(form_code)}"


def copy_url(form_code: str):
    resolved_url = get_resolved_url(form_code)
    return rx.set_clipboard(resolved_url)


def form_editor():
    markdown_styles = {
        "h2": {
            "margin_bottom": "0.5em",  # Reduce space after h2
        },
        "h3": {
            "margin_top": "0.5em",  # Reduce space before h3
            "margin_bottom": "0.5em",  # Reduce space after h3
        },
        "ol": {
            "margin_top": "0.5em",  # Control list spacing
        },
    }

    return rx.vstack(
        rx.cond(
            FormEditorState.form_id != "",
            rx.hstack(
                rx.text("Survey Name", weight="bold"),  # Bold label
                rx.input(
                    placeholder="Survey Name (e.g., 'My Survey')",
                    value=FormEditorState.temp_name,
                    on_change=FormEditorState.set_temp_name,  # Update temp_name on change
                    flex="1",  # Make the input grow to fill available space
                ),
                rx.button(
                    "Rename",
                    on_click=FormEditorState.set_name(
                        FormEditorState.temp_name
                    ),  # Update name on click
                    color_scheme="blue",
                ),
                align="center",
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                rx.text("", weight="bold"),  # Default text for new survey
            ),
        ),
        # Action Buttons Section (Second Line)
        rx.cond(
            FormEditorState.form_id != "",
            rx.hstack(
                rx.tooltip(
                    rx.button(
                        rx.icon("link"),
                        "Copy URL",
                        on_click=lambda: copy_url(FormEditorState.form.code),
                        type="button",
                    ),
                    content="Copy the survey URL to clipboard. You can give this URL to survey participants.",
                ),
                rx.tooltip(
                    rx.button(
                        rx.icon("eye"),
                        "Preview",
                        on_click=rx.redirect(
                            routes.show_form(FormEditorState.form.code)
                            + "?preview=yes",
                            external=True,
                        ),
                        type="button",
                    ),
                    content="Preview the survey as it will appear to participants. The results are not saved.",
                ),
                rx.tooltip(
                    rx.button(
                        "View Results",
                        on_click=rx.redirect(
                            routes.form_responses(FormEditorState.form.id)
                        ),
                    ),
                    content="View the results of the survey.",
                ),
                rx.tooltip(
                    rx.button(
                        "Copy Survey",
                        on_click=FormEditorState.copy_survey,
                        type="button",
                        color_scheme="blue",
                    ),
                    content="Create a copy of this survey. The copy will have the same questions, page breaks, and plain texts.",
                ),
                rx.spacer(),
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(
                        rx.button("Delete Survey", color_scheme="tomato"),
                    ),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("Delete Survey"),
                        rx.alert_dialog.description(
                            "Are you sure you want to delete this survey?"
                        ),
                        rx.flex(
                            rx.alert_dialog.cancel(rx.button("Cancel")),
                            rx.spacer(),
                            rx.alert_dialog.action(
                                rx.button(
                                    "Delete", on_click=FormEditorState.delete_form
                                )
                            ),
                        ),
                    ),
                ),
                spacing="2",
                align="center",
                justify="start",
                width="100%",
            ),
            rx.markdown(
                """
                ### Create a new survey
                - Enter the name of the survey in the input field below "Create Survey" on the menu.
                - Click the "New Survey" button to create a new survey.

                ### Edit an existing survey
                - Select your created surveys on the menu.
                """,
                custom_styles=markdown_styles,
            ),
        ),
        rx.divider(),
        rx.foreach(
            FormEditorState.form.fields,
            field_edit_view,
        ),
        spacing="4",  # Add spacing between sections
    )


def form_entry_title():
    from debriefly.reflex.form_designer.pages import FormEntryState

    form_name = rx.cond(
        rx.State.form_id == "",
        utils.quoted_var("New Survey"),
        rx.cond(
            FormEntryState.form,
            FormEntryState.form.name,
            utils.quoted_var("Unknown Survey"),
        ),
    )
    return f"{constants.TITLE} | {form_name}"


def form_edit_title():
    form_name = rx.cond(
        rx.State.form_id == "",
        utils.quoted_var("New Survey"),
        rx.cond(
            FormEditorState.form,
            FormEditorState.form.name,
            utils.quoted_var("Unknown Survey"),
        ),
    )
    return f"{constants.TITLE} | {form_name}"
