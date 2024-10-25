import json
import csv
import io
import logging
import reflex as rx
from debriefly.reflex.form_designer import constants, routes, style, utils
from debriefly.reflex.form_designer.components import field_prompt
from debriefly.reflex.backend.models import Form, Response, FieldValue
from debriefly.reflex.backend.backend import MainState as AppState

logger = logging.getLogger(__name__)

message_style = dict(
    display="inline-block",
    padding="1em",
    border_radius="8px",
    max_width=["30em", "30em", "50em", "50em", "50em", "50em"],
)


class ResponsesState(AppState):
    form: Form = Form()
    responses: list[Response] = []
    # { response_id: { field_id: list_of_messages, ... }, ... }
    # where list_of_messages is a list of dicts with keys "role" and "content"
    response_debriefings: dict[int, dict[int, list[dict[str, str]]]] = {}

    @rx.var
    def index_is_current(self) -> bool:
        if self.form_id == "":
            return False
        with rx.session() as session:
            return session.get(Form, self.form_id).index_is_current()

    @rx.var
    def index_is_available(self) -> bool:
        if self.form_id == "":
            return False
        with rx.session() as session:
            return session.get(Form, self.form_id).index_is_available()

    async def index(self):
        if self.form_id != "":
            logger.info(f"Starting indexing for form {self.form_id}")
            with rx.session() as session:
                form = session.get(Form, self.form_id)
                form.index()
                session.add(form)
                session.commit()
            return rx.toast.success(
                "Indexing complete. Please refresh the page in a couple of minutes and the Analyze button should be available."
            )

    def load_responses(self):
        with rx.session() as session:
            form = session.get(Form, self.form_id)
            if not self._user_has_access(form) or form is None:
                self.form = Form()
                return
            self.form = form
            self.responses = session.exec(
                Response.select().where(Response.form_id == self.form_id)
            ).all()

            for response in self.responses:
                response_debriefings = {}
                for field_value in response.field_values:
                    if field_value.debriefing is not None:
                        response_debriefings[field_value.field_id] = json.loads(
                            field_value.debriefing
                        )
                    else:
                        response_debriefings[field_value.field_id] = []
                self.response_debriefings[response.id] = response_debriefings

    def delete_response(self, id: int):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.delete(session.get(Response, id))
            session.commit()
            return ResponsesState.load_responses

    def download(self):
        with io.StringIO() as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Response ID",
                    "Submitted",
                    "Client Token",
                    "Question",
                    "Answer",
                    "Debriefing",
                ]
            )
            for response in self.responses:
                for field_value in response.field_values:
                    fields = [
                        response.id,
                        response.ts,
                        response.client_token,
                        field_value.field.name,
                        field_value.value,
                        field_value.debriefing,
                    ]
                    writer.writerow(fields)
            return rx.download(
                data=f.getvalue(), filename=f"{self.form.name}_responses.csv"
            )


def debriefing_transcript(response: Response, field_value: FieldValue):
    return rx.vstack(
        rx.foreach(
            ResponsesState.response_debriefings[response.id][field_value.field_id],
            lambda message: rx.cond(
                message["role"] == "assistant",
                rx.box(
                    rx.markdown(
                        message["content"],
                        background_color=rx.color("accent", 4),
                        color=rx.color("accent", 12),
                        **message_style,
                    ),
                    text_align="left",
                    padding_top="1em",
                    width="100%",
                ),
                rx.box(
                    rx.markdown(
                        message["content"],
                        background_color=rx.color("mauve", 4),
                        color=rx.color("mauve", 12),
                        **message_style,
                    ),
                    text_align="right",
                    margin_top="1em",
                    width="100%",
                ),
            ),
        ),
    )


def response_content(response: Response):
    return rx.vstack(
        rx.moment(value=response.ts),
        rx.foreach(
            response.field_values,
            lambda fv: rx.vstack(
                field_prompt(fv.field),
                rx.cond(
                    fv.value != "",
                    rx.text(fv.value),
                    rx.text("No response provided."),
                ),
                rx.cond(
                    fv.field.debriefing,
                    debriefing_transcript(response, fv),
                    rx.spacer(),
                ),
                align="start",
            ),
        ),
        gap="2em",
    )


def response(r: Response):
    return rx.accordion.item(
        header=rx.hstack(
            rx.text(r.client_token),
            rx.tooltip(
                rx.button(
                    rx.icon(tag="x", size=16),
                    color_scheme="tomato",
                    margin_right="1em",
                    on_click=ResponsesState.delete_response(r.id),
                ),
                content="Delete this Response",
            ),
            justify="between",
            align="center",
        ),
        content=response_content(r),
        value=r.id.to(str),
    )


def responses_title():
    form_name = rx.cond(
        rx.State.form_id == "",
        utils.quoted_var("Unknown Form"),
        ResponsesState.form.name,
    )
    return f"{constants.TITLE} | {form_name} | Responses"


def responses_analysis_title():
    form_name = rx.cond(
        rx.State.form_id == "",
        utils.quoted_var("Unknown Form"),
        ResponsesState.form.name,
    )
    return f"{constants.TITLE} | {form_name} | Analysis"


def responses_accordion(**props):
    return rx.accordion.root(
        rx.foreach(
            ResponsesState.responses,
            response,
        ),
        collapsible=True,
        type="multiple",
        **props,
    )


def responses_page(**props):
    return style.layout(
        rx.link("< Edit", href=routes.edit_form(ResponsesState.form.id)),
        rx.flex(
            rx.heading(ResponsesState.form.name),
            rx.spacer(),
            rx.cond(
                ResponsesState.index_is_current,
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(
                        rx.button(rx.icon("refresh-ccw"), color_scheme="green"),
                    ),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("Update Index"),
                        rx.alert_dialog.description(
                            "The index is current and doesn't need to be updated. Are you sure you want to update it?"
                        ),
                        rx.flex(
                            rx.alert_dialog.cancel(rx.button("Cancel")),
                            rx.spacer(),
                            rx.alert_dialog.action(
                                rx.button("Update", on_click=ResponsesState.index)
                            ),
                        ),
                    ),
                ),
                rx.button(
                    rx.icon("refresh-ccw"),
                    color_scheme="tomato",
                    on_click=ResponsesState.index,
                ),
            ),
            rx.tooltip(
                rx.button(
                    rx.icon("play"),
                    disabled=~ResponsesState.index_is_available,
                    on_click=rx.redirect(
                        routes.form_responses_analyze(ResponsesState.form.id)
                    ),
                ),
                content="Analyze",
            ),
            rx.tooltip(
                rx.button(rx.icon("download"), on_click=ResponsesState.download),
                content="Download CSV",
            ),
            spacing="1",
        ),
        responses_accordion(
            variant="outline",
            radius="small",
        ),
    )
