import json
import csv
import io
import logging
import reflex as rx
from sqlmodel import select
from debriefly.reflex.form_designer import constants, routes, style, utils
from debriefly.reflex.form_designer.components import field_prompt
from debriefly.reflex.backend.models import (
    Form,
    QualtricsEmbedSession,
    Response,
    FieldType,
    FieldValue,
)
from debriefly.reflex.backend.backend import MainState as AppState

logger = logging.getLogger(__name__)

message_style = dict(
    display="inline-block",
    padding="1em",
    border_radius="8px",
    max_width=["30em", "30em", "50em", "50em", "50em", "50em"],
)


def bundle_item_key(item) -> str:
    return str(item.value or item.label or item.id)


def bundle_answer_map(raw_value: str) -> dict[str, str]:
    try:
        answers = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return {}

    if isinstance(answers, dict):
        return {str(key): str(value) for key, value in answers.items()}
    if not isinstance(answers, list):
        return {}

    mapped = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        value = answer.get("value")
        response = answer.get("response")
        if value is not None and response is not None:
            mapped[str(value)] = str(response)
    return mapped


def transcript_messages(raw_transcript: str | None) -> list[dict[str, str]]:
    if not raw_transcript:
        return []

    try:
        messages = json.loads(raw_transcript)
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(messages, list):
        return []

    cleaned = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        if role and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


class ResponsesState(AppState):
    form: Form = Form()
    responses: list[Response] = []
    qualtrics_embed_sessions: list[QualtricsEmbedSession] = []
    # { response_id: { field_id: list_of_messages, ... }, ... }
    # where list_of_messages is a list of dicts with keys "role" and "content"
    response_debriefings: dict[int, dict[int, list[dict[str, str]]]] = {}
    # { qualtrics_embed_session.public_id: list_of_messages, ... }
    qualtrics_debriefings: dict[str, list[dict[str, str]]] = {}

    @rx.var
    def index_is_current(self) -> bool:
        if self.form_id == "":
            return False
        with rx.session() as session:
            form = session.get(Form, self.form_id)
            if form is None:
                return False
            return form.index_is_current()

    @rx.var
    def index_is_available(self) -> bool:
        if self.form_id == "":
            return False
        with rx.session() as session:
            form = session.get(Form, self.form_id)
            if form is None:
                return False
            return form.index_is_available()

    # added to disable RAG when there are no chat responses
    @rx.var
    def has_chat_responses(self) -> bool:
        debriefly_responses = any(
            any(messages for messages in debriefings.values())
            for debriefings in self.response_debriefings.values()
        )
        return debriefly_responses or any(
            messages for messages in self.qualtrics_debriefings.values()
        )

    @rx.var
    def has_qualtrics_embed_sessions(self) -> bool:
        return len(self.qualtrics_embed_sessions) > 0

    async def index(self):
        if self.form_id != "":
            if not self.has_chat_responses:
                return rx.toast.info(
                    "No chat responses available to analyze. Please collect responses with chat."
                )
            elif self.index_is_current:
                if not self.index_is_available:
                    return rx.toast.info(
                        "Please wait for a couple of minutes for the index to be available."
                    )
            else:
                logger.info(f"Starting indexing for form {self.form_id}")
                with rx.session() as session:
                    form = session.get(Form, self.form_id)
                    form.index()
                    session.add(form)
                    session.commit()
                return rx.toast.info(
                    "Please wait for a couple of minutes for the index to be created."
                )

    def load_responses(self):
        with rx.session() as session:
            self.response_debriefings = {}  # reset debriefings
            self.qualtrics_debriefings = {}
            self.qualtrics_embed_sessions = []
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

            self.qualtrics_embed_sessions = session.exec(
                select(QualtricsEmbedSession)
                .where(QualtricsEmbedSession.form_id == form.id)
                .order_by(QualtricsEmbedSession.created_at)
            ).all()
            self.qualtrics_debriefings = {
                embed_session.public_id: transcript_messages(embed_session.transcript)
                for embed_session in self.qualtrics_embed_sessions
            }

    def delete_response(self, id: int):
        if not self._user_has_access():
            return
        with rx.session() as session:
            session.delete(session.get(Response, id))
            session.commit()
            return ResponsesState.load_responses

    def download(self):
        fields = [
            f
            for f in self.form.fields
            if f.type_ not in (FieldType.static, FieldType.pagebreak)
        ]

        header = [
            "Response ID",
            "Submitted",
            "Client Token",
        ]
        for field in fields:
            if field.bundled:
                for item in field.bundle_items:
                    header.append(f"{field.name}_{item.label or item.value or item.id}")
            else:
                header.append(field.name)
            if field.debriefing:
                header.append(f"{field.name}_debriefing")

        with io.StringIO() as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for response in self.responses:
                row = [
                    response.id,
                    response.ts,
                    response.client_token,
                ]
                for field in fields:
                    field_value = [
                        fv for fv in response.field_values if fv.field.id == field.id
                    ]

                    if len(field_value) == 0:
                        if field.bundled:
                            row.extend([""] * len(field.bundle_items))
                        else:
                            row.append("")
                        if field.debriefing:
                            row.append("")
                    else:
                        if field.bundled:
                            answers = bundle_answer_map(field_value[0].value)
                            for item in field.bundle_items:
                                row.append(answers.get(bundle_item_key(item), ""))
                        else:
                            row.append(field_value[0].value)
                        if field.debriefing:
                            row.append(field_value[0].debriefing)

                writer.writerow(row)

            return rx.download(
                data=f.getvalue(), filename=f"{self.form.name}_responses.csv"
            )

    def download_transcripts(self):
        transcript_text = ""
        for response in self.responses:
            transcript_text += f"--- Response {response.client_token} ---\n\n"
            for field in self.form.fields:
                if field.debriefing:  # Only process debriefing fields
                    messages = self.response_debriefings.get(response.id, {}).get(
                        field.id, []
                    )
                    if messages:  # Only include fields with chat content
                        transcript_text += f"Field: {field.name}\n\n"
                        for msg in messages:
                            if msg["role"] == "user":
                                transcript_text += f"User: {msg['content']}\n\n"
                            elif msg["role"] == "assistant":
                                transcript_text += f"Assistant: {msg['content']}\n\n"
                        transcript_text += "\n"  # Extra newline after each field's chat
            transcript_text += "\n"  # Extra newline between responses

        for embed_session in self.qualtrics_embed_sessions:
            messages = self.qualtrics_debriefings.get(embed_session.public_id, [])
            if not messages:
                continue

            transcript_text += (
                f"--- Qualtrics Interview {embed_session.public_id} ---\n\n"
            )
            if embed_session.external_response_id:
                transcript_text += (
                    f"Qualtrics Response ID: "
                    f"{embed_session.external_response_id}\n\n"
                )
            if embed_session.external_question_id:
                transcript_text += (
                    f"Qualtrics Question ID: "
                    f"{embed_session.external_question_id}\n\n"
                )
            transcript_text += f"Question: {embed_session.question_text}\n\n"
            transcript_text += f"Answer: {embed_session.response_text}\n\n"
            for msg in messages:
                if msg["role"] == "user":
                    transcript_text += f"User: {msg['content']}\n\n"
                elif msg["role"] == "assistant":
                    transcript_text += f"Assistant: {msg['content']}\n\n"
            transcript_text += "\n"

        filename = f"{self.form.name}_transcripts.txt"
        return rx.download(data=transcript_text, filename=filename)


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


def qualtrics_embed_transcript(embed_session: QualtricsEmbedSession):
    return rx.vstack(
        rx.foreach(
            ResponsesState.qualtrics_debriefings[embed_session.public_id.to(str)],
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


def qualtrics_embed_content(embed_session: QualtricsEmbedSession):
    return rx.vstack(
        rx.hstack(
            rx.text("Transcript ID:", weight="bold"),
            rx.code(embed_session.public_id),
            align="center",
        ),
        rx.cond(
            embed_session.external_response_id != "",
            rx.hstack(
                rx.text("Qualtrics Response ID:", weight="bold"),
                rx.text(embed_session.external_response_id),
                align="center",
            ),
            rx.fragment(),
        ),
        rx.cond(
            embed_session.external_question_id != "",
            rx.hstack(
                rx.text("Qualtrics Question ID:", weight="bold"),
                rx.text(embed_session.external_question_id),
                align="center",
            ),
            rx.fragment(),
        ),
        rx.box(
            rx.text("Question", weight="bold"),
            rx.markdown(embed_session.question_text),
            width="100%",
        ),
        rx.box(
            rx.text("Answer", weight="bold"),
            rx.markdown(embed_session.response_text),
            width="100%",
        ),
        qualtrics_embed_transcript(embed_session),
        align="start",
        gap="1em",
    )


def qualtrics_embed_response(embed_session: QualtricsEmbedSession):
    return rx.accordion.item(
        header=rx.hstack(
            rx.text(
                rx.cond(
                    embed_session.external_response_id != "",
                    embed_session.external_response_id,
                    embed_session.public_id,
                )
            ),
            rx.cond(
                embed_session.completed,
                rx.badge("Complete", color_scheme="green"),
                rx.badge("Started", color_scheme="yellow"),
            ),
            justify="between",
            align="center",
        ),
        content=qualtrics_embed_content(embed_session),
        value=embed_session.public_id,
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


def qualtrics_embed_accordion(**props):
    return rx.accordion.root(
        rx.foreach(
            ResponsesState.qualtrics_embed_sessions,
            qualtrics_embed_response,
        ),
        collapsible=True,
        type="multiple",
        **props,
    )


def responses_page(**props):
    return style.layout(
        rx.link("< Edit", href=routes.edit_form(ResponsesState.form.id)),
        rx.vstack(
            rx.heading(f"Results for {ResponsesState.form.name}"),
            rx.hstack(
                # RAG component is disabled for now
                # rx.tooltip(
                #    rx.cond(
                #        ResponsesState.index_is_current
                #        & ResponsesState.index_is_available
                #        & ResponsesState.has_chat_responses,
                #        rx.button(
                #            rx.hstack(
                #                rx.icon("play"),
                #                rx.text("Analyze Chats with AI"),
                #                spacing="2",
                #            ),
                #            on_click=rx.redirect(
                #                routes.form_responses_analyze(ResponsesState.form.id)
                #            ),
                #        ),
                #        rx.cond(
                #            ResponsesState.has_chat_responses,
                #            rx.button(
                #                rx.hstack(
                #                    rx.icon("play"),
                #                    rx.text("Analyze Chats with AI"),
                #                    spacing="2",
                #                ),
                #                on_click=ResponsesState.index,
                #            ),
                #            rx.button(
                #                rx.hstack(
                #                    rx.icon("play"),
                #                    rx.text("Analyze Chats with AI"),
                #                    spacing="2",
                #                ),
                #                color_scheme="gray",
                #                on_click=ResponsesState.index,
                #            ),
                #        ),
                #    ),
                #    content="Analyze Debriefing Transcripts with AI",
                # ),
                rx.tooltip(
                    rx.button(
                        rx.hstack(
                            rx.icon("download"),
                            rx.text("Download Results"),
                            spacing="2",
                        ),
                        color_scheme="green",
                        on_click=ResponsesState.download,
                    ),
                    content="Download all the results (including metadata) as CSV",
                ),
                rx.tooltip(
                    rx.button(
                        rx.hstack(
                            rx.icon("file-text"),
                            rx.text("Download Chats"),
                            spacing="2",
                        ),
                        color_scheme="purple",
                        on_click=ResponsesState.download_transcripts,
                    ),
                    content="Download chat transcripts as one .txt file. You can paste this to LLM (e.g., ChatGPT) to analyze.",
                ),
                spacing="3",
            ),
            spacing="3",
        ),
        responses_accordion(
            variant="outline",
            radius="small",
        ),
        rx.cond(
            ResponsesState.has_qualtrics_embed_sessions,
            rx.vstack(
                rx.heading("Qualtrics Embedded Interviews", size="4"),
                rx.text(
                    "These chats were collected from Qualtrics embeds. "
                    "Qualtrics stores the transcript ID; Debriefly stores the full chat."
                ),
                qualtrics_embed_accordion(
                    variant="outline",
                    radius="small",
                    width="100%",
                ),
                width="100%",
                spacing="3",
                margin_top="2em",
            ),
            rx.fragment(),
        ),
    )
