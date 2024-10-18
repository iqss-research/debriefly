import json

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

logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class ChatState(MainState):
    loaded: bool = False
    form_id2: int = -1  # populated on on_load
    field_value_id: int = -1  # populated on on_load
    client_token: str  # populated on on_load
    chat: list[QA]
    processing: bool = False
    done: bool = False  # done with current chat?
    system_message: str
    initial_message: str

    async def on_load(self):

        logger.info("ChatState on_load")
        self.done = False

        state = await self.get_state(FormEntryState)
        self.client_token = state.client_token
        self.form_id2 = state.form.id
        logger.info(
            f"Loading debriefing response for response {self.client_token} and form {state.form.id}"
        )

        with rx.session() as session:
            response_id = (
                session.exec(
                    select(Response)
                    .where(Response.client_token == self.client_token)
                    .where(Response.form_id == self.form_id2)
                )
                .first()
                .id
            )
            logger.info(f"Obtained response_id: {response_id}")

            state = await self.get_state(FormEntryTabState)
            field_id = state.fields[state.active_tab][0].id
            field_type = state.fields[state.active_tab][0].type_
            field_value = session.exec(
                select(FieldValue)
                .where(FieldValue.response_id == response_id)
                .where(FieldValue.field_id == field_id)
            ).first()
            field_value_id = field_value.id
            field_value_value_id = field_value.value

            if field_type in (FieldType.radio, FieldType.checkbox):
                field_value_label = (
                    session.exec(
                        select(Option)
                        .where(Option.field_id == field_id)
                        .where(
                            or_(
                                Option.value == field_value_value_id,
                                Option.label == field_value_value_id,
                            )
                        )
                    )
                    .first()
                    .label
                )
            else:
                field_value_label = field_value_value_id
            logger.info(
                f"Obtained {field_id=}, {field_value_id=}, {field_value_label=} for debriefing"
            )
            self.field_value_id = field_value_id
            self.loaded = True

            env = Environment(
                loader=PackageLoader("debriefly.data.templates", package_path=""),
                autoescape=select_autoescape(),
            )

            debriefing_field_prompt = (
                session.exec(select(Field).where(Field.id == field_id)).first().prompt
            )
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
            self.chat = [QA(question="", answer=self.initial_message)]

    async def process_question(self, form_data: dict[str, str]):
        question = form_data["question"]
        if question == "":
            return

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
        # seen to be raised on content filtering
        except openai.BadRequestError as e:
            logger.error(f"OpenAI API error: {e}")
            # remove the last user message that caused the error
            self.chat = self.chat[:-1]
            self.processing = False
            return

        # Stream the results, yielding after every word.
        for item in session:
            if len(item.choices) == 0:
                continue
            if hasattr(item.choices[0].delta, "content"):
                answer_text = item.choices[0].delta.content
                # Ensure answer_text is not None before concatenation
                if answer_text is not None:
                    self.chat[-1].answer += answer_text
                else:
                    # Handle the case where answer_text is None, perhaps log it or assign a default value
                    # For example, assigning an empty string if answer_text is None
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

                # filter out any system messages and save to db
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
                        routes.show_form(self.form_id2) + "?continue=true"
                    )
                else:
                    logger.info("Redirecting to done screen")
                    yield rx.redirect(routes.FORM_ENTRY_SUCCESS)

        # Toggle the processing flag.
        self.processing = False
