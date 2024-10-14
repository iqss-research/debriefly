import json
import reflex as rx
from debriefly.reflex.form_designer import constants, routes, style, utils
from debriefly.reflex.form_designer.components import field_prompt
from debriefly.reflex.backend.models import Form, Response, FieldValue
from debriefly.reflex.backend.backend import MainState as AppState


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
                    response_debriefings[field_value.field_id] = json.loads(
                        field_value.debriefing
                    )
                self.response_debriefings[response.id] = response_debriefings

    def delete_response(self, id: int):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.delete(session.get(Response, id))
            session.commit()
            return ResponsesState.load_responses


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
        rx.center(rx.heading(ResponsesState.form.name)),
        responses_accordion(
            variant="outline",
            radius="small",
        ),
    )
