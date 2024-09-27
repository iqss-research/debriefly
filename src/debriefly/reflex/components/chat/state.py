import json
import reflex as rx
from sqlmodel import select
from jinja2 import Environment, PackageLoader, select_autoescape
import logging
from debriefly.openai import get_client
from debriefly.reflex.backend.backend import State as BackendState
from debriefly.reflex.backend.models import Question, Answer


logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class ChatState(BackendState):
    answer_id: int
    question_id: int
    chat: list[QA]
    question: str
    processing: bool = False
    done: bool = False
    system_message: str
    initial_message: str

    def load_survey_answer(self, answer_id):
        logger.info(f"Loading survey answer {answer_id}")
        self.answer_id = answer_id
        with rx.session() as session:
            answer = session.exec(select(Answer).where(Answer.id == answer_id)).first()
            if answer is not None:
                question = session.exec(
                    select(Question).where(Question.id == answer.question_id)
                ).first()
                logger.info(f"Setting question id {question.id}")
                self.question_id = question.id

                kwargs = {
                    "question": question.question_text,
                    "response": answer.answer,
                    "end_of_survey_token": "<end_of_survey>",
                }
                env = Environment(
                    loader=PackageLoader("debriefly.data.templates", package_path=""),
                    autoescape=select_autoescape(),
                )

                self.system_message = env.get_template("system_message.jinja").render(
                    **kwargs
                )
                self.initial_message = env.get_template("initial_message.jinja").render(
                    **kwargs
                )
                self.chat = [QA(question="", answer=self.initial_message)]

    def on_load(self):
        self.load_survey_answer(self.router.page.params.get("a_id"))

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
                answer = session.exec(
                    select(Answer).where(Answer.id == self.answer_id)
                ).first()

                # filter out any system messages and save to db
                messages = [msg for msg in messages if msg["role"] != "system"]
                answer.debriefing = json.dumps(messages)
                session.add(answer)
                session.commit()

        # Toggle the processing flag.
        self.processing = False
