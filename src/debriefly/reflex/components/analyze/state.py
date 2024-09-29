import time
import reflex as rx
from sqlmodel import select
import logging
from debriefly.reflex.backend.models import Question
from debriefly.openai import AzureOpenAISearch
from debriefly.reflex.backend.backend import MainState

logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class State(MainState):
    question_id: int
    debriefing_transcripts: list[str]
    chat: list[QA]
    processing: bool = False
    uploading: bool = False
    done: bool = False

    async def load_survey_debriefings(self, question_id):
        logger.info(f"Loading debriefings for question {question_id}")
        self.question_id = question_id
        with rx.session() as session:
            question = session.exec(
                select(Question).where(Question.id == question_id)
            ).first()
            if question is not None:
                self.debriefing_transcripts = question.debriefing_transcripts()

                client = AzureOpenAISearch(
                    index_name="debriefly-temp",
                    api_key=self.config["AZURE_OPENAI_API_KEY"],
                    api_version=self.config["AZURE_OPENAI_API_VERSION"],
                    api_endpoint=self.config["AZURE_OPENAI_ENDPOINT"],
                    api_model=self.config["AZURE_OPENAI_DEPLOYMENT_MODEL"],
                    search_key=self.config["AZURE_OPENAI_SEARCH_KEY"],
                    search_endpoint=self.config["AZURE_OPENAI_SEARCH_ENDPOINT"],
                )

                # There's a time lag between when we upload documents
                # and when we can query them.
                self.uploading = True
                yield
                logger.info("Uploading debriefing transcripts")
                client.upload(self.debriefing_transcripts)
                logger.info("Waiting 20 seconds")
                time.sleep(20)
                logger.info("Debriefing transcripts uploaded")
                self.uploading = False

    async def process_question(self, form_data: dict[str, str]):
        question = form_data["question"]
        if question == "":
            return

        model = self.openai_process_question
        async for value in model(question):
            yield value

    async def openai_process_question(self, question: str):

        self.chat.append(QA(question=question, answer=""))

        self.processing = True
        yield

        messages = []
        for qa in self.chat:
            messages.append({"role": "user", "content": qa.question})
            messages.append({"role": "assistant", "content": qa.answer})
        messages = messages[:-1]

        client = AzureOpenAISearch(
            index_name="debriefly-temp",
            api_key=self.config["AZURE_OPENAI_API_KEY"],
            api_version=self.config["AZURE_OPENAI_API_VERSION"],
            api_endpoint=self.config["AZURE_OPENAI_ENDPOINT"],
            api_model=self.config["AZURE_OPENAI_DEPLOYMENT_MODEL"],
            search_key=self.config["AZURE_OPENAI_SEARCH_KEY"],
            search_endpoint=self.config["AZURE_OPENAI_SEARCH_ENDPOINT"],
        )

        extra_body = {
            "data_sources": [
                {
                    "type": "azure_search",
                    "parameters": {
                        "endpoint": client.azure_search_service_endpoint,
                        "index_name": client.index_name,
                        "authentication": {
                            "type": "api_key",
                            "key": client.admin_key,
                        },
                    },
                }
            ],
        }

        session = client.openai_client.client.chat.completions.create(
            model=client.openai_client.model,
            messages=messages,
            temperature=client.openai_client.temperature,
            stream=True,
            extra_body=extra_body,
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

        if client.openai_client.end_token in self.chat[-1].answer:
            self.done = True
            self.chat[-1].answer = self.chat[-1].answer.replace(client.end_token, "")

        # Toggle the processing flag.
        self.processing = False
