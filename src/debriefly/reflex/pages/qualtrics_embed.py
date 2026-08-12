import json
import logging
from datetime import datetime, timezone

import openai
import reflex as rx
from jinja2 import Environment, PackageLoader, select_autoescape
from sqlmodel import select

from debriefly.openai import get_client
from debriefly.interview_provenance import merge_model_version, snapshot_interview
from debriefly.reflex.backend.models import (
    Form,
    QualtricsEmbedSession,
    UserOpenAISettings,
)
from debriefly.reflex.components.chat.loading_icon import loading_icon
from debriefly.reflex.components.chat.state import QA
from reflex_chakra import form as chakra_form, form_control as chakra_form_control


logger = logging.getLogger(__name__)

QUALTRICS_EMBED_ROUTE = "/qualtrics/embed"
END_TOKEN = "<end_of_chat>"


def _query_param(params: dict, *names: str) -> str:
    for name in names:
        value = params.get(name)
        if isinstance(value, list):
            value = value[0] if value else ""
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _safe_origin(value: str) -> str:
    if value.startswith("https://") or value.startswith("http://"):
        return value
    return "*"


def _messages_to_chat(messages: list[dict[str, str]], initial_message: str) -> list[QA]:
    chat = [QA(question="", answer=initial_message)]
    pending_user = ""
    for message in messages[1:]:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "user":
            pending_user = content
        elif role == "assistant":
            chat.append(QA(question=pending_user, answer=content))
            pending_user = ""
    if pending_user:
        chat.append(QA(question=pending_user, answer=""))
    return chat


class QualtricsEmbedState(rx.State):
    loaded: bool = False
    processing: bool = False
    done: bool = False
    error: str = ""

    form_code: str = ""
    this_form_id: int = -1
    session_public_id: str = ""
    parent_origin: str = "*"
    external_response_id: str = ""
    external_question_id: str = ""
    question_text: str = ""
    response_text: str = ""

    system_message: str = ""
    initial_message: str = ""
    configured_model: str = ""
    api_reported_model_versions: str = ""
    chat: list[QA]

    def _post_message(self, event_type: str, extra: dict | None = None):
        payload = {
            "source": "debriefly",
            "type": f"debriefly:{event_type}",
            "sessionId": self.session_public_id,
            "transcriptId": self.session_public_id,
            "completed": self.done,
            "error": self.error,
        }
        if extra:
            payload.update(extra)
        script = (
            "window.parent && window.parent.postMessage("
            f"{json.dumps(payload)}, {json.dumps(self.parent_origin)}"
            ");"
        )
        return rx.call_script(script)

    def _current_messages(self) -> list[dict[str, str]]:
        messages = [{"role": "assistant", "content": self.initial_message}]
        for qa in self.chat[1:]:
            if qa.question:
                messages.append({"role": "user", "content": qa.question})
            if qa.answer:
                messages.append({"role": "assistant", "content": qa.answer})
        return messages

    def _record_api_model_version(self, model_version: str | None) -> None:
        versions = merge_model_version(
            self.api_reported_model_versions,
            model_version,
        )
        if versions == self.api_reported_model_versions:
            return

        self.api_reported_model_versions = versions
        with rx.session() as session:
            record = session.exec(
                select(QualtricsEmbedSession).where(
                    QualtricsEmbedSession.public_id == self.session_public_id
                )
            ).first()
            if record is None:
                return
            record.interview_model_versions = versions
            session.add(record)
            session.commit()

    def _save_transcript(self, completed: bool = False):
        if not self.session_public_id:
            return

        with rx.session() as session:
            record = session.exec(
                select(QualtricsEmbedSession).where(
                    QualtricsEmbedSession.public_id == self.session_public_id
                )
            ).first()
            if record is None:
                return

            record.transcript = json.dumps(self._current_messages())
            record.interview_model_versions = self.api_reported_model_versions
            record.completed = completed
            record.updated_at = datetime.now(timezone.utc)
            session.add(record)
            session.commit()

    async def on_load(self):
        logger.info("QualtricsEmbedState on_load")
        self.loaded = False
        self.processing = False
        self.done = False
        self.error = ""
        self.session_public_id = ""
        self.configured_model = ""
        self.api_reported_model_versions = ""
        self.chat = []

        params = self.router.page.params
        self.form_code = _query_param(params, "form_code", "form")
        self.question_text = _query_param(params, "question", "question_text")
        self.response_text = _query_param(params, "response", "answer")
        self.external_question_id = _query_param(params, "qid", "question_id")
        self.external_response_id = _query_param(
            params, "response_id", "rid", "respondent_id"
        )
        self.parent_origin = _safe_origin(_query_param(params, "origin"))
        requested_session_id = _query_param(params, "session_id", "transcript_id")

        if not self.form_code:
            self.error = "Missing Debriefly form code."
        elif not self.question_text:
            self.error = "Missing question text."
        elif not self.response_text:
            self.error = "Answer the Qualtrics question before starting the interview."

        if self.error:
            self.loaded = True
            return self._post_message("error")

        env = Environment(
            loader=PackageLoader("debriefly.data.templates", package_path=""),
            autoescape=select_autoescape(),
        )
        kwargs = {
            "question": self.question_text,
            "response": self.response_text,
            "is_bundled_question": False,
            "subquestions": [],
            "subquestions_text": "",
            "end_of_survey_token": END_TOKEN,
        }
        self.system_message = env.get_template("system_message.jinja").render(**kwargs)
        self.initial_message = env.get_template("initial_message.jinja").render(
            **kwargs
        )
        self.chat = [QA(question="", answer=self.initial_message)]

        with rx.session() as session:
            form = session.exec(select(Form).where(Form.code == self.form_code)).first()
            if form is None:
                self.error = "The Debriefly form code is not valid."
                self.loaded = True
                return self._post_message("error")

            settings = UserOpenAISettings.get_for_user(session, form.user_id)
            if settings is None or not settings.is_configured:
                self.error = (
                    "This Debriefly form is not ready for embedded interviews. "
                    "Please ask the survey owner to add an OpenAI API key."
                )
                self.loaded = True
                return self._post_message("error")

            self.this_form_id = form.id
            record = None
            if requested_session_id:
                record = session.exec(
                    select(QualtricsEmbedSession)
                    .where(QualtricsEmbedSession.public_id == requested_session_id)
                    .where(QualtricsEmbedSession.form_id == form.id)
                ).first()

            if record is None:
                client = get_client(
                    missing_ok=False,
                    initial_message=self.initial_message,
                    system_message=self.system_message,
                    api_key=settings.api_key,
                    api_model=settings.model,
                )
                record = QualtricsEmbedSession(
                    form_id=form.id,
                    external_response_id=self.external_response_id,
                    external_question_id=self.external_question_id,
                    question_text=self.question_text,
                    response_text=self.response_text,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                snapshot_interview(record, client)
                self.configured_model = client.model
                self.system_message = client.system_message
                self.initial_message = client.initial_message
            else:
                record.updated_at = datetime.now(timezone.utc)
                self.external_response_id = record.external_response_id
                self.external_question_id = record.external_question_id
                self.question_text = record.question_text
                self.response_text = record.response_text
                if record.interview_model:
                    self.configured_model = record.interview_model
                    self.api_reported_model_versions = record.interview_model_versions
                    self.system_message = record.interview_system_prompt
                    self.initial_message = record.interview_initial_prompt
                    self.chat = [QA(question="", answer=self.initial_message)]
                elif not record.transcript:
                    client = get_client(
                        missing_ok=False,
                        initial_message=self.initial_message,
                        system_message=self.system_message,
                        api_key=settings.api_key,
                        api_model=settings.model,
                    )
                    snapshot_interview(record, client)
                    self.configured_model = client.model
                    self.system_message = client.system_message
                    self.initial_message = client.initial_message
                elif not record.completed:
                    # Continuing a legacy interview would mix untracked prior
                    # turns with a newly configured model and prompt.
                    self.error = (
                        "This interview began before model and prompt tracking "
                        "was enabled and cannot be resumed. Please start a new "
                        "interview."
                    )
                if record.transcript:
                    try:
                        messages = json.loads(record.transcript)
                    except json.JSONDecodeError:
                        messages = []
                    if isinstance(messages, list) and messages:
                        self.chat = _messages_to_chat(messages, self.initial_message)
                self.done = record.completed

            session.add(record)
            session.commit()
            session.refresh(record)
            self.session_public_id = record.public_id

        self.loaded = True
        if self.error:
            return self._post_message("error")
        return self._post_message("ready")

    async def process_question(self, form_data: dict[str, str]):
        question = (form_data.get("question") or "").strip()
        if self.error or self.done or self.processing or not question:
            return

        self.chat.append(QA(question=question, answer=""))
        self.processing = True
        yield

        with rx.session() as session:
            form = session.get(Form, self.this_form_id)
            settings = (
                UserOpenAISettings.get_for_user(session, form.user_id)
                if form is not None
                else None
            )
            if settings is None or not settings.is_configured:
                self.processing = False
                self.error = "This embedded interview is not configured."
                yield self._post_message("error")
                return
            api_key = settings.api_key
            api_model = self.configured_model or settings.model

        client = get_client(
            missing_ok=False,
            initial_message=self.initial_message,
            system_message=self.system_message,
            api_key=api_key,
            api_model=api_model,
            append_end_token_instruction=False,
        )

        messages = [
            {"role": "system", "content": client.system_message},
            {"role": "assistant", "content": client.initial_message},
        ]
        for qa in self.chat[1:]:
            messages.append({"role": "user", "content": qa.question})
            messages.append({"role": "assistant", "content": qa.answer})
        messages = messages[:-1]

        try:
            completion = client.client.chat.completions.create(
                model=client.model,
                messages=messages,
                temperature=client.temperature,
                stream=True,
            )
        except openai.OpenAIError as exc:
            logger.error("OpenAI API error during Qualtrics embed chat: %s", exc)
            self.chat = self.chat[:-1]
            self.processing = False
            self.error = "The interview could not contact OpenAI."
            yield self._post_message("error")
            return

        for item in completion:
            # Persist the provider-reported version as soon as it appears so
            # provenance survives a later stream interruption.
            self._record_api_model_version(getattr(item, "model", None))
            if len(item.choices) == 0:
                continue
            if hasattr(item.choices[0].delta, "content"):
                answer_text = item.choices[0].delta.content or ""
                self.chat[-1].answer += answer_text
                self.chat = self.chat
                yield

        if END_TOKEN in self.chat[-1].answer:
            self.done = True
            self.chat[-1].answer = self.chat[-1].answer.replace(END_TOKEN, "")

        self.processing = False
        self._save_transcript(completed=self.done)
        if self.done:
            yield self._post_message("complete")

    async def finish_chat(self):
        if self.processing or self.done:
            return

        self.done = True
        self._save_transcript(completed=True)
        yield self._post_message("complete")


message_style = dict(
    display="inline-block",
    padding="0.75rem 0.875rem",
    border_radius="8px",
    max_width="min(42rem, 92%)",
)


def message(qa: QA) -> rx.Component:
    return rx.box(
        rx.cond(
            qa.question != "",
            rx.box(
                rx.markdown(
                    qa.question,
                    background_color=rx.color("mauve", 4),
                    color=rx.color("mauve", 12),
                    **message_style,
                ),
                text_align="right",
                margin_top="0.75rem",
            ),
        ),
        rx.box(
            rx.markdown(
                qa.answer,
                background_color=rx.color("accent", 4),
                color=rx.color("accent", 12),
                **message_style,
            ),
            text_align="left",
            padding_top="0.75rem",
        ),
        width="100%",
    )


def chat_messages() -> rx.Component:
    return rx.box(
        rx.foreach(QualtricsEmbedState.chat, message),
        width="100%",
        padding="0.75rem",
        padding_bottom="5.5rem",
        overflow_y="auto",
        flex="1",
    )


def action_bar() -> rx.Component:
    return rx.box(
        chakra_form(
            chakra_form_control(
                rx.hstack(
                    rx.input(
                        rx.input.slot(rx.icon("message-circle", size=18)),
                        placeholder="Type your answer",
                        name="question",
                        id="qualtrics_embed_question",
                        width="100%",
                    ),
                    rx.button(
                        rx.cond(
                            QualtricsEmbedState.processing,
                            loading_icon(height="1em"),
                            rx.icon("send", size=18),
                        ),
                        type="submit",
                        aria_label="Send",
                    ),
                    rx.button(
                        rx.icon("check", size=18),
                        type="button",
                        variant="outline",
                        aria_label="Finish interview",
                        on_click=QualtricsEmbedState.finish_chat,
                    ),
                    width="100%",
                    spacing="2",
                ),
                is_disabled=QualtricsEmbedState.processing | QualtricsEmbedState.done,
            ),
            on_submit=QualtricsEmbedState.process_question,
            reset_on_submit=True,
        ),
        position="sticky",
        bottom="0",
        left="0",
        width="100%",
        padding="0.75rem",
        border_top=f"1px solid {rx.color('mauve', 4)}",
        background_color=rx.color("mauve", 2),
    )


def embed_ui() -> rx.Component:
    return rx.cond(
        ~QualtricsEmbedState.loaded,
        rx.center(rx.spinner(), min_height="20rem"),
        rx.cond(
            QualtricsEmbedState.error != "",
            rx.center(
                rx.box(
                    rx.text(QualtricsEmbedState.error),
                    padding="1rem",
                    text_align="center",
                    color=rx.color("tomato", 11),
                ),
                min_height="14rem",
            ),
            rx.vstack(
                chat_messages(),
                rx.cond(
                    QualtricsEmbedState.done,
                    rx.box(
                        rx.hstack(
                            rx.icon("circle-check-big", size=18),
                            rx.text("Interview complete. You can continue."),
                            spacing="2",
                        ),
                        padding="0.75rem",
                        border_top=f"1px solid {rx.color('mauve', 4)}",
                        background_color=rx.color("grass", 3),
                        color=rx.color("grass", 12),
                        width="100%",
                    ),
                    action_bar(),
                ),
                align_items="stretch",
                width="100%",
                min_height="20rem",
            ),
        ),
    )


@rx.page(
    route=QUALTRICS_EMBED_ROUTE,
    title="Debriefly Interview",
    on_load=QualtricsEmbedState.on_load,
)
def qualtrics_embed() -> rx.Component:
    return rx.box(
        embed_ui(),
        width="100%",
        min_height="20rem",
        background_color=rx.color("mauve", 1),
    )
