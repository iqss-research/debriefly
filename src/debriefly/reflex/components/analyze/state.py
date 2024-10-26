import reflex as rx
import logging
from debriefly.openai import AzureOpenAISearch
from debriefly.reflex.form_designer.pages.response import ResponsesState

logger = logging.getLogger(__name__)


class QA(rx.Base):
    question: str
    answer: str


class AnalysisState(ResponsesState):
    chat: list[QA]
    processing: bool = False
    done: bool = False

    async def on_load(self):
        super().load_responses()
        self.chat = []
        self.processing = False
        self.done = False

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

        logger.info(f"Querying index {self.form.index_name}")
        client = AzureOpenAISearch(
            index_name=self.form.index_name,
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

            # Delete the index
            client = AzureOpenAISearch(
                index_name=self.form.index_name,
                api_key=self.config["AZURE_OPENAI_API_KEY"],
                api_version=self.config["AZURE_OPENAI_API_VERSION"],
                api_endpoint=self.config["AZURE_OPENAI_ENDPOINT"],
                api_model=self.config["AZURE_OPENAI_DEPLOYMENT_MODEL"],
                search_key=self.config["AZURE_OPENAI_SEARCH_KEY"],
                search_endpoint=self.config["AZURE_OPENAI_SEARCH_ENDPOINT"],
            )
            logger.info(f"Deleting index {self.form.index_name}")
            client.delete_index()

        # Toggle the processing flag.
        self.processing = False
