import json
from typing import Optional
import time
from datetime import datetime, timezone

import openai
import reflex as rx
from sqlmodel import select, or_
from jinja2 import Environment, PackageLoader, select_autoescape
import logging
from debriefly.openai import get_client
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import (
    Response,
    FieldValue,
    Field,
    Option,
    FieldType,
)
from debriefly.reflex.form_designer.pages.form_entry import (
    FormEntryState,
    FormEntryTabState,
)
from debriefly.reflex.form_designer import routes

import asyncio

logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class ChatState(MainState):
    chat_start_time: Optional[float] = None  # Unix timestamp when chat starts
    loaded: bool = False
    this_form_id: int = -1  # populated on on_load
    this_form_code: str = ""  # populated on on_load
    field_value_id: int = -1  # populated on on_load
    client_token: str  # populated on on_load
    chat: list[QA]
    processing: bool = False
    done: bool = False  # done with current chat?
    system_message: str
    initial_message: str
    field: Field = Field(
        min_debriefing_time=0, max_debriefing_time=0
    )  # Default value to avoid None
    show_finish: bool = False  # New state variable to control visibility
    show_force_finish: bool = False  # Allow forced finish if max time exceeded
    is_preview: bool = FormEntryState.is_preview  # Inherit from FormEntryState

    last_activity_time: float = 0.0  # timestamp of last keystroke
    elapsed_time: int = 0  # accumulated seconds
    paused: bool = False  # true when idle > 60s

    @rx.var
    def elapsed_time_str(self) -> str:
        m, s = divmod(self.elapsed_time, 60)
        return f"{int(m):02d}:{int(s):02d}"

    @rx.var
    def min_time_str(self) -> str:
        m = (self.field.min_debriefing_time or 0) // 60
        return f"{m:02d}:00"

    @rx.var
    def max_time_str(self) -> str:
        m = (self.field.max_debriefing_time or 0) // 60
        return f"{m:02d}:00"

    @rx.background
    async def count_time(self):
        while not self.done:
            now = time.time()
            idle = now - self.last_activity_time
            async with self:
                if idle >= 60:
                    # user idle: pause timer
                    self.paused = True
                else:
                    # not idle: tick once per second
                    if not self.paused:
                        self.elapsed_time += 1
                        # console trace
                        logger.info(
                            f"[chat {self.client_token}] "
                            f"elapsed={self.elapsed_time}s "
                            f"(min={self.field.min_debriefing_time}, "
                            f"max={self.field.max_debriefing_time}, "
                            f"paused={self.paused})"
                        )
                        # show finish/force-finish as before, but based on elapsed_time
                        if self.elapsed_time > self.field.min_debriefing_time:
                            self.paused = False
                            self.show_finish = True
                        if (
                            self.field.max_debriefing_time > 0
                            and self.elapsed_time >= self.field.max_debriefing_time
                        ):
                            self.show_finish = False
                            self.show_force_finish = True
                            self.paused = False
            await asyncio.sleep(1)

    async def on_load(self):
        logger.info("ChatState on_load")
        self.done = False
        self.chat_start_time = time.time()
        self.show_finish = False
        self.show_force_finish = False

        state = await self.get_state(FormEntryState)
        self.client_token = state._ensure_client_token()
        self.this_form_id = state.form.id
        self.this_form_code = state.form.code
        logger.info(
            f"Loading debriefing response for response {self.client_token} and form {state.form.id}"
        )
        now = time.time()
        self.last_activity_time = now
        self.elapsed_time = 0
        self.paused = False

        with rx.session() as session:
            response = session.exec(
                select(Response)
                .where(Response.client_token == self.client_token)
                .where(Response.form_id == self.this_form_id)
            ).first()
            if response is None:
                # Create a new Response if none exists
                response = Response(
                    client_token=self.client_token,
                    form_id=self.this_form_id,
                    ts=datetime.now(timezone.utc),
                )
                session.add(response)
                session.commit()
                session.refresh(response)
                logger.info(f"Created new response with ID {response.id}")
            response_id = response.id
            logger.info(f"Obtained response_id: {response_id}")

            state = await self.get_state(FormEntryTabState)
            field_id = state.fields[state.active_tab][-1].id
            self.field = session.exec(select(Field).where(Field.id == field_id)).first()
            if self.field is None:
                logger.error(f"No field found with ID {field_id}")
                self.loaded = True
                return
            field_type = self.field.type_
            field_value = session.exec(
                select(FieldValue)
                .where(FieldValue.response_id == response_id)
                .where(FieldValue.field_id == field_id)
            ).first()
            if field_value is None:
                logger.error(
                    f"No field value found for field ID {field_id} and response ID {response_id}"
                )
                self.loaded = True
                return
            self.field_value_id = field_value.id
            field_value_value_id = field_value.value

            if field_type in (FieldType.radio, FieldType.checkbox):
                option = session.exec(
                    select(Option)
                    .where(Option.field_id == field_id)
                    .where(
                        or_(
                            Option.value == field_value_value_id,
                            Option.label == field_value_value_id,
                        )
                    )
                ).first()
                if option is None:
                    field_value_label = field_value_value_id
                else:
                    field_value_label = option.label
            else:
                field_value_label = field_value_value_id
            logger.info(
                f"Obtained {field_id=}, {self.field_value_id=}, {field_value_label=} for debriefing"
            )
            logger.info(
                f"chat_start_time: {self.chat_start_time}, min_debriefing_time: {self.field.min_debriefing_time}"
            )
            if self.field.min_debriefing_time == 0:
                self.show_finish = True
                self.paused = False
            if self.field.max_debriefing_time == 0:
                self.show_finish = False
                self.show_force_finish = True
            self.loaded = True
            logger.info(f"ChatState loaded: self.loaded = {self.loaded}")

            env = Environment(
                loader=PackageLoader("debriefly.data.templates", package_path=""),
                autoescape=select_autoescape(),
            )

            debriefing_field_prompt = self.field.prompt
            debriefing_field_value = field_value_label

            kwargs = {
                "question": debriefing_field_prompt,
                "response": debriefing_field_value,
                "end_of_survey_token": "<end_of_chat>",
            }
            self.system_message = env.get_template("system_message.jinja").render(
                **kwargs
            )
            self.initial_message = env.get_template("initial_message.jinja").render(
                **kwargs
            )

            # load custom system and initial messages if they exist
            if self.field.custom_system_message:
                tmpl = env.from_string(self.field.custom_system_message)
                self.system_message = tmpl.render(**kwargs)

            if self.field.custom_initial_message:
                tmpl = env.from_string(self.field.custom_initial_message)
                self.initial_message = tmpl.render(**kwargs)

            self.chat = [QA(question="", answer=self.initial_message)]

            if (
                not self.show_force_finish
                and self.field.min_debriefing_time > 0
                and self.field.max_debriefing_time > 0
            ):
                return ChatState.count_time()

    async def process_question(self, form_data: dict[str, str]):
        question = form_data.get("question")
        if question is None or question == "":
            return

        self.last_activity_time = time.time()
        if self.paused:
            self.paused = False

        model = self.openai_process_question
        async for value in model(question):
            yield value

    async def openai_process_question(self, question: str):
        client = get_client(
            initial_message=self.initial_message,
            system_message=self.system_message,
            api_key=self.config["AZURE_OPENAI_API_KEY"],
            api_version=self.config["AZURE_OPENAI_API_VERSION"],
            api_endpoint=self.config["AZURE_OPENAI_ENDPOINT"],
            api_model=self.config["AZURE_OPENAI_DEPLOYMENT_MODEL"],
        )

        # Add the question to the list of questions.
        qa = QA(question=question, answer="")
        self.chat.append(qa)

        # Clear the input and start the processing.
        self.processing = True
        yield

        messages = [
            {
                "role": "system",
                "content": client.system_message,
            },
            {
                "role": "assistant",
                "content": client.initial_message,
            },
        ]
        for qa in self.chat[1:]:
            messages.append({"role": "user", "content": qa.question})
            messages.append({"role": "assistant", "content": qa.answer})

        # Remove the last mock answer.
        messages = messages[:-1]

        try:
            session = client.client.chat.completions.create(
                model=client.model,
                messages=messages,
                temperature=client.temperature,
                stream=True,
            )
        except openai.BadRequestError as e:
            logger.error(f"OpenAI API error: {e}")
            # Remove the last user message that caused the error
            self.chat = self.chat[:-1]
            self.processing = False
            return

        # Stream the results, yielding after every word.
        for item in session:
            if len(item.choices) == 0:
                continue
            if hasattr(item.choices[0].delta, "content"):
                answer_text = item.choices[0].delta.content
                if answer_text is not None:
                    self.chat[-1].answer += answer_text
                else:
                    answer_text = ""
                    self.chat[-1].answer += answer_text
                self.chat = self.chat
                yield

        if client.end_token in self.chat[-1].answer:
            self.done = True
            self.chat[-1].answer = self.chat[-1].answer.replace(client.end_token, "")

            with rx.session() as session:
                field_value = session.exec(
                    select(FieldValue).where(FieldValue.id == self.field_value_id)
                ).first()

                # Filter out system messages and save to db
                messages = [msg for msg in messages if msg["role"] != "system"]
                field_value.debriefing = json.dumps(messages)
                session.add(field_value)
                session.commit()

                logger.info("Saved debriefing to db")
                state = await self.get_state(FormEntryTabState)
                await state.advance()
                if not state.is_beyond_last_tab:
                    logger.info("Continuing to form entry page")
                    yield rx.redirect(
                        routes.show_form(self.this_form_code) + "?continue=yes"
                    )
                else:
                    state = await self.get_state(FormEntryState)
                    if state.is_preview:
                        logger.info("Preview mode, deleting saved response")
                        with rx.session() as session:
                            response = session.exec(
                                select(Response)
                                .where(
                                    Response.client_token
                                    == state._ensure_client_token()
                                )
                                .where(Response.form_id == state.form.id)
                            ).first()
                            if response is not None:
                                session.delete(response)
                                session.commit()
                    logger.info("Redirecting to done screen")
                    yield rx.redirect(routes.FORM_ENTRY_SUCCESS)

        # Toggle the processing flag.
        self.processing = False

    async def on_unload(self):
        self.done = True

    async def finish_chat(self):

        self.done = True
        with rx.session() as session:
            field_value = session.exec(
                select(FieldValue).where(FieldValue.id == self.field_value_id)
            ).first()
            # Save the current chat messages
            messages = [
                {"role": "assistant", "content": self.initial_message},
            ]
            for qa in self.chat[1:]:
                messages.append({"role": "user", "content": qa.question})
                messages.append({"role": "assistant", "content": qa.answer})
            field_value.debriefing = json.dumps(messages)
            session.add(field_value)
            session.commit()

            logger.info("Saved debriefing to db")
            state = await self.get_state(FormEntryTabState)
            await state.advance()
            if not state.is_beyond_last_tab:
                logger.info("Continuing to form entry page")
                yield rx.redirect(
                    routes.show_form(self.this_form_code) + "?continue=yes"
                )
            else:
                state = await self.get_state(FormEntryState)
                if state.is_preview:
                    logger.info("Preview mode, deleting saved response")
                    with rx.session() as session:
                        response = session.exec(
                            select(Response)
                            .where(
                                Response.client_token == state._ensure_client_token()
                            )
                            .where(Response.form_id == state.form.id)
                        ).first()
                        if response is not None:
                            session.delete(response)
                            session.commit()
                logger.info("Redirecting to done screen")
                yield rx.redirect(routes.FORM_ENTRY_SUCCESS)
