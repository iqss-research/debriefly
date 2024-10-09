import json
import reflex as rx
from sqlmodel import select
from jinja2 import Environment, PackageLoader, select_autoescape
import logging
from debriefly.openai import get_client
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import Response, FieldValue, Field
from debriefly.reflex.form_designer.pages.form_entry import FormEntryState

logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class ChatState(MainState):
    client_token: str
    field_value_ids: list[int]
    chat: list[QA]
    processing: bool = False
    done: bool = False
    system_message: str
    initial_message: str

    current_field_value_id: int

    async def on_load(self):
        state = await self.get_state(FormEntryState)
        self.client_token = state.client_token
        logger.info(f"Loading debriefing fields for response {self.client_token}")
        with rx.session() as session:
            response = session.exec(
                select(Response).where(Response.client_token == self.client_token)
            ).first()
            form = response.form

            debriefing_field_ids = [f.id for f in form.fields if f.debriefing]
            print(f"{debriefing_field_ids=}")
            debriefing_field_value_ids = []
            for field_value in session.exec(
                select(FieldValue)
                .where(FieldValue.response_id == response.id)
                .where(FieldValue.field_id.in_(debriefing_field_ids))
            ):
                debriefing_field_value_ids.append(field_value.id)
            print(f"{debriefing_field_value_ids=}")

            if len(debriefing_field_value_ids) < 1 or len(debriefing_field_ids) < 1:
                print("No debriefing fields found")
                return rx.toast.success("Thank you.")

            env = Environment(
                loader=PackageLoader("debriefly.data.templates", package_path=""),
                autoescape=select_autoescape(),
            )

            for field_id, field_value_id in zip(
                debriefing_field_ids, debriefing_field_value_ids
            ):
                self.current_field_value_id = field_value_id
                debriefing_field_prompt = (
                    session.exec(select(Field).where(Field.id == field_id))
                    .first()
                    .prompt
                )
                debriefing_field_value = (
                    session.exec(
                        select(FieldValue).where(FieldValue.id == field_value_id)
                    )
                    .first()
                    .value
                )

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

            return rx.toast.success("Debriefing completed. Thank you.")

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

        session = client.client.chat.completions.create(
            model=client.model,
            messages=messages,
            temperature=client.temperature,
            stream=True,
        )

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
                    select(FieldValue).where(
                        FieldValue.id == self.current_field_value_id
                    )
                ).first()

                # filter out any system messages and save to db
                messages = [msg for msg in messages if msg["role"] != "system"]
                field_value.debriefing = json.dumps(messages)
                session.add(field_value)
                session.commit()

        # Toggle the processing flag.
        self.processing = False
