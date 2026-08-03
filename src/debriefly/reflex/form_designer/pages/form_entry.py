import logging
import json
from datetime import datetime, timezone
import reflex as rx
from sqlmodel import select
from debriefly.reflex.form_designer import routes, style
from debriefly.reflex.form_designer.components import field_view
from debriefly.reflex.backend.models import FieldType, Field, FieldValue, Form, Response

Missing = object()
logger = logging.getLogger(__name__)


def bundle_item_key(item) -> str:
    return str(item.value or item.label or item.id)


def bundle_field_input_name(field: Field, item) -> str:
    return f"{field.name}___{item.id}"


def bundle_option_input_name(field: Field, item, option) -> str:
    return f"{field.name}___{item.id}___{option.id}"


def option_label_for_value(field: Field, value: str) -> str:
    for option in field.options:
        option_value = str(option.value or option.label or option.id)
        if value in {option_value, option.value, option.label, str(option.id)}:
            return option.label or option_value
    return str(value)


def field_type_value(field: Field) -> str:
    return field.type_.value if isinstance(field.type_, FieldType) else str(field.type_)


def bundled_item_response(field: Field, item, form_data):
    if field.type_ == FieldType.checkbox:
        selected = []
        for option in field.options:
            key = bundle_option_input_name(field, item, option)
            value = form_data.get(key, Missing)
            if value is not Missing:
                selected.append(option_label_for_value(field, str(value)))
        return ", ".join(selected) if selected else Missing

    key = bundle_field_input_name(field, item)
    value = form_data.get(key, Missing)
    if value is Missing and field.type_ == FieldType.scale and field.required:
        value = field.scale_min
    if value is Missing:
        return Missing
    if field.type_ == FieldType.radio:
        return option_label_for_value(field, str(value))
    return str(value)


class FormEntryState(rx.State):
    form: Form = Form()
    client_token: str = rx.Cookie("")
    is_preview: bool = False
    current_scale_values: dict[str, int] = {}
    pending_debriefing_field_id: int = -1

    def set_scale_value(self, name: str, v: str):
        """Store the value coming from the slider (string → int)."""
        if v:  # v is a Radix/BaseVar, still str-ish
            self.current_scale_values[name] = int(v)

    def _ensure_client_token(self):
        if self.client_token == "":
            self.client_token = self.router.session.client_token
        return self.client_token

    def load_form(self):
        if self.router.page.params.get("preview"):
            self.is_preview = True
            logger.info("Running in preview mode")

        if self.form_code != "":
            self.load_form_by_code(self.form_code)
        else:
            self.form = Form()

    def load_form_by_code(self, code: str):
        with rx.session() as session:
            self.form = session.exec(select(Form).where(Form.code == code)).first()

    def notify_parent_survey_complete(self):
        payload = {
            "source": "debriefly",
            "type": "debriefly:survey_complete",
            "status": "complete",
            "submissionId": self._ensure_client_token(),
        }
        return rx.call_script(
            "window.parent && window.parent.postMessage("
            f"{json.dumps(payload)}, '*');"
        )

    async def handle_submit(self, form_data):
        logger.info("Handling form submission")
        # A chat is valid only after this submission commits successfully.
        self.pending_debriefing_field_id = -1
        tab_state = await self.get_state(FormEntryTabState)
        if not 0 <= tab_state.active_tab < len(tab_state.fields):
            logger.warning(
                "Ignoring stale form submission for tab %s (available tabs: %s)",
                tab_state.active_tab,
                len(tab_state.fields),
            )
            return rx.toast.error(
                "This survey page changed before it was saved. Please reload it."
            )
        active_fields = list(tab_state.fields[tab_state.active_tab])
        debriefing_fields = [field for field in active_fields if field.debriefing]
        # Get the first debriefing field
        debriefing_field = debriefing_fields[0] if len(debriefing_fields) > 0 else None

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
                session.add(response)
                session.flush()

            # only consider fields that were submitted as part of the tab (page)
            for field in active_fields:
                # delete any previously-submitted field values
                field_values = session.exec(
                    select(FieldValue)
                    .where(FieldValue.field_id == field.id)
                    .where(FieldValue.response_id == response.id)
                ).all()
                for field_value in field_values:
                    session.delete(field_value)

                # Add replacements directly to the session. The response's
                # selectin-loaded relationship can still contain a value after a
                # later query autoflushes its deletion; cascading through that
                # collection again raises "Instance ... has been deleted".
                if field.bundled:
                    bundle_answers = []
                    for item in field.bundle_items:
                        item_response = bundled_item_response(field, item, form_data)
                        if item_response is not Missing:
                            bundle_answers.append(
                                {
                                    "label": item.label,
                                    "value": bundle_item_key(item),
                                    "response": item_response,
                                }
                            )
                    if bundle_answers:
                        session.add(
                            FieldValue(
                                field_id=field.id,
                                response_id=response.id,
                                value=json.dumps(bundle_answers),
                            )
                        )
                else:
                    value = form_data.get(field.name, Missing)
                    if value is not Missing:
                        session.add(
                            FieldValue(
                                field_id=field.id,
                                response_id=response.id,
                                value=value,
                            )
                        )
                    elif field.type_ == FieldType.checkbox:
                        for option in field.options:
                            key = f"{field.name}___{option.value or option.label or option.id}"
                            value = form_data.get(key, Missing)
                            if value is not Missing:
                                session.add(
                                    FieldValue(
                                        field_id=field.id,
                                        response_id=response.id,
                                        value=form_data[key],
                                    )
                                )

            response.ts = datetime.now(timezone.utc)
            # Existing responses are persistent, and new responses were flushed
            # above, so the timestamp and direct child additions are tracked.
            # A page submission is one unit of work. Committing inside the field
            # loop held more connections and exposed partially-saved pages.
            session.commit()

        if debriefing_field is not None:
            if debriefing_field.id is not None:
                self.pending_debriefing_field_id = debriefing_field.id
            logger.info("Redirecting to chat")
            return rx.redirect(routes.FORM_ENTRY_CHAT)
        elif "done" in form_data:
            logger.info("Done with survey")

            if self.is_preview:
                logger.info("Preview mode, deleting saved response")
                with rx.session() as session:
                    response = session.exec(
                        select(Response)
                        .where(Response.client_token == self._ensure_client_token())
                        .where(Response.form_id == self.form.id)
                    ).first()
                    if response is not None:
                        session.delete(response)
                        session.commit()

            # If the last question shown was a static question, assume
            # that it's some sort of 'Thank you' message. If not, redirect
            # to our custom 'done' screen
            # -> disable this logic after v.4.5.0 since we added "show_submission_code" to the form model
            # if tab_state.fields[tab_state.active_tab][-1].type_ == FieldType.static:
            #    return rx.toast.success(
            #        "Thank you. You can now close this browser window."
            #    )
            # else:
            #    logger.info("Redirecting to done screen")
            #    return rx.redirect(routes.FORM_ENTRY_SUCCESS)

            return rx.redirect(routes.FORM_ENTRY_SUCCESS)
        else:
            logger.info("Advancing to next tab")
            await tab_state.advance()


class FormEntryTabState(rx.State):
    fields: list[list[Field]] = []
    tab_back_enabled: list[bool] = []
    n_tabs: int = 0
    active_tab: int = 0
    is_last_tab: bool = False
    is_beyond_last_tab: bool = False
    can_go_back: bool = False

    # Markdown fields have a provision of having placeholders
    # (e.g. `{submission_id}`) that are evaluated at runtime
    # This dict holds a mapping of string field id to such markdown values
    markdowns: dict[str, str] = {}

    @staticmethod
    def split_fields_into_tabs(
        fields: list[Field],
    ) -> tuple[list[list[Field]], list[bool]]:
        """Group fields into respondent pages and track page-break back settings."""
        tabs: list[list[Field]] = []
        tab_back_enabled: list[bool] = []
        this_group_fields: list[Field] = []
        group_back_enabled = False
        last_split_was_debriefing = False

        for field in fields:
            if field_type_value(field) == FieldType.pagebreak.value:
                if this_group_fields:
                    tabs.append(this_group_fields)
                    tab_back_enabled.append(group_back_enabled)
                    this_group_fields = []
                    last_split_was_debriefing = False

                if tabs and not last_split_was_debriefing:
                    group_back_enabled = bool(field.allow_back)
                else:
                    group_back_enabled = False
                continue

            this_group_fields.append(field)

            if bool(field.debriefing):
                tabs.append(this_group_fields)
                tab_back_enabled.append(group_back_enabled)
                this_group_fields = []
                group_back_enabled = False
                last_split_was_debriefing = True

        if this_group_fields:
            tabs.append(this_group_fields)
            tab_back_enabled.append(group_back_enabled)

        return tabs, tab_back_enabled

    @staticmethod
    def tab_can_go_back(
        fields: list[list[Field]], tab_back_enabled: list[bool], active_tab: int
    ) -> bool:
        if active_tab <= 0 or active_tab >= len(fields):
            return False
        if active_tab >= len(tab_back_enabled) or not tab_back_enabled[active_tab]:
            return False
        return True

    def _refresh_navigation(self):
        self.is_last_tab = self.active_tab >= self.n_tabs - 1
        self.is_beyond_last_tab = self.active_tab >= self.n_tabs
        self.can_go_back = self.tab_can_go_back(
            self.fields, self.tab_back_enabled, self.active_tab
        )

    async def on_load(self):
        logger.info("FormEntryTabState on_load")
        if self.router.page.params.get("continue"):
            logger.info("Continuing from previous tab")
            return

        self.fields = []
        self.tab_back_enabled = []
        self.n_tabs = 0

        state = await self.get_state(FormEntryState)
        form = state.form
        if form is not None:

            # Break fields in "pages", with page breaks after any debriefing
            # field, or any explicit `pagebreak` field.
            for field in form.fields:

                if field_type_value(field) == FieldType.static.value:
                    self.markdowns[str(field.id)] = field.prompt.format(
                        **self.markdown_variables()
                    )
                else:
                    self.markdowns[str(field.id)] = ""

            self.fields, self.tab_back_enabled = self.split_fields_into_tabs(
                form.fields
            )

            self.n_tabs = len(self.fields)
        self.active_tab = 0
        self._refresh_navigation()

    async def advance(self):
        logger.info("Advancing to next tab")
        self.active_tab += 1
        self._refresh_navigation()

    async def previous(self):
        logger.info("Moving to previous tab")
        if self.can_go_back:
            self.active_tab -= 1
            self._refresh_navigation()

    def markdown_variables(self) -> dict[str, str]:
        return dict(
            submission_id=self.router.session.client_token,
        )


def form_entry_tab(fields: list[Field], i: int):
    return rx.tabs.content(
        rx.vstack(
            rx.foreach(
                fields,
                lambda field: field_view(
                    field, markdown=FormEntryTabState.markdowns[field.id.to_string()]
                ),
            )
        ),
        value=f"tab_{i}",
    )


def form_entry_page():
    return style.layout(
        rx.form(
            rx.cond(
                FormEntryState.is_preview,
                rx.hstack(
                    rx.button(
                        "Close Survey (Preview Only)",
                        on_click=rx.call_script("window.close()"),
                        color_scheme="green",
                        variant="solid",
                        padding="0.75em 1.5em",
                        font_size="lg",
                        _hover={"background_color": "green.600"},
                    ),
                    justify="space_between",
                    width="100%",
                    margin_bottom="1em",
                ),
            ),
            rx.vstack(
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
                    rx.hstack(
                        rx.cond(
                            FormEntryTabState.can_go_back,
                            rx.button(
                                rx.icon("arrow-left", size=16),
                                "Back",
                                type="button",
                                variant="outline",
                                on_click=FormEntryTabState.previous,
                            ),
                            rx.fragment(),
                        ),
                        rx.button("Submit", type="submit"),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.cond(
                            FormEntryTabState.can_go_back,
                            rx.button(
                                rx.icon("arrow-left", size=16),
                                "Back",
                                type="button",
                                variant="outline",
                                on_click=FormEntryTabState.previous,
                            ),
                            rx.fragment(),
                        ),
                        rx.button("Next", type="submit"),
                        spacing="2",
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
