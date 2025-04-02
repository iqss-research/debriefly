import logging
from datetime import datetime, timezone
import reflex as rx
from sqlmodel import select
from debriefly.reflex.form_designer import routes, style
from debriefly.reflex.form_designer.components import field_view
from debriefly.reflex.backend.models import FieldType, Field, FieldValue, Form, Response

Missing = object()
logger = logging.getLogger(__name__)


class FormEntryState(rx.State):
    form: Form = Form()
    client_token: str = rx.Cookie("")
    is_preview: bool = False

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

    async def handle_submit(self, form_data):
        logger.info("Handling form submission")
        tab_state = await self.get_state(FormEntryTabState)
        debriefing_fields = [
            f for f in tab_state.fields[tab_state.active_tab] if f.debriefing
        ]
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

            # only consider fields that were submitted as part of the tab (page)
            for field in tab_state.fields[tab_state.active_tab]:
                # delete any previously-submitted field values
                field_value = session.exec(
                    select(FieldValue)
                    .where(FieldValue.field_id == field.id)
                    .where(FieldValue.response_id == response.id)
                ).first()
                if field_value is not None:
                    session.delete(field_value)

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

                response.ts = datetime.now(timezone.utc)
                session.add(response)
                session.commit()

        if debriefing_field is not None:
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
            #if tab_state.fields[tab_state.active_tab][-1].type_ == FieldType.static:
            #    return rx.toast.success(
            #        "Thank you. You can now close this browser window."
            #    )
            #else:
            #    logger.info("Redirecting to done screen")
            #    return rx.redirect(routes.FORM_ENTRY_SUCCESS)

            return rx.redirect(routes.FORM_ENTRY_SUCCESS)
        else:
            logger.info("Advancing to next tab")
            await tab_state.advance()


class FormEntryTabState(rx.State):
    fields: list[list[Field]] = []
    n_tabs: int = 0
    active_tab: int = 0
    is_last_tab: bool = False
    is_beyond_last_tab: bool = False

    # Markdown fields have a provision of having placeholders
    # (e.g. `{submission_id}`) that are evaluated at runtime
    # This dict holds a mapping of string field id to such markdown values
    markdowns: dict[str, str] = {}

    async def on_load(self):
        logger.info("FormEntryTabState on_load")
        if self.router.page.params.get("continue"):
            logger.info("Continuing from previous tab")
            return

        self.fields = []
        self.n_tabs = 0

        state = await self.get_state(FormEntryState)
        form = state.form
        if form is not None:

            # Break fields in "pages", with page breaks after any debriefing
            # field, or any explicit `pagebreak` field.
            this_group_fields = []
            for field in form.fields:

                if field.type_ == FieldType.static:
                    self.markdowns[str(field.id)] = field.prompt.format(
                        **self.markdown_variables()
                    )
                else:
                    self.markdowns[str(field.id)] = ""

                if (field.type_ == FieldType.pagebreak) or bool(field.debriefing):
                    if field.type_ != FieldType.pagebreak:
                        this_group_fields.append(field)
                    if len(this_group_fields) > 0:
                        self.fields.append(this_group_fields)
                    this_group_fields = []
                else:
                    this_group_fields.append(field)

            if this_group_fields:
                self.fields.append(this_group_fields)

            self.n_tabs = len(self.fields)
        self.active_tab = 0
        self.is_last_tab = self.n_tabs == 1

    async def advance(self):
        logger.info("Advancing to next tab")
        self.active_tab += 1
        self.is_last_tab = self.active_tab >= self.n_tabs - 1
        self.is_beyond_last_tab = self.active_tab >= self.n_tabs

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
                    rx.button("Submit", type="submit"),
                    rx.button("Next", type="submit"),
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
