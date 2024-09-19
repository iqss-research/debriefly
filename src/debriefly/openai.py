import os
from functools import cache
import logging
from rich.console import Console
from rich.prompt import Prompt
from rich.live import Live
import time
from openai import OpenAI, AzureOpenAI

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
)

logger = logging.getLogger(__name__)


class Client:
    """
    A class that encapsulates
     - an OpenAI client
     - a model name (str)
     - an optional system message (str)
     - an initial message (str)
     - the temperature of the model (float)
     - an end_token (str) to detect the end of the conversation
    and can be used to interactively chat with the OpenAI model.
    """

    def __init__(
        self,
        initial_message="",
        system_message="",
        temperature=0.7,
        end_token="<end_of_chat>",
    ):
        self.client = self.model = None
        self.initial_message = initial_message
        self.temperature = temperature
        self.end_token = end_token

        self.system_message = (
            system_message
            + f"\nInclude the special {self.end_token} token in the response to end the chat."
        )

        if "AZURE_OPENAI_API_KEY" in os.environ:
            logger.debug("Instantiating AzureOpenAI client")
            self.client = AzureOpenAI(
                api_version=os.environ["AZURE_OPENAI_API_VERSION"],
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            )
            self.model = os.environ["AZURE_OPENAI_DEPLOYMENT_MODEL"]
        elif "OPENAI_ORG_ID" in os.environ:
            logger.debug("Instantiating OpenAI client")
            self.client = OpenAI(
                organization=os.environ["OPENAI_ORG_ID"],
                project=os.environ["OPENAI_PROJECT_ID"],
            )
            self.model = "gpt-4o-mini"
        else:
            raise ValueError("No OpenAI client found")

    def complete(self, user_input, chat_history, stream=True, extra_body=None):
        messages = [{"role": "system", "content": self.system_message}]
        for human_input, assistant_response in chat_history:
            if human_input is not None:
                messages.append({"role": "user", "content": human_input})
            messages.append({"role": "assistant", "content": assistant_response})
        messages.append({"role": "user", "content": user_input})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stream=stream,
            extra_body=extra_body,
        )

        if stream:
            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        else:
            yield response.choices[0].message.content

    def interactive_chat(self, delay=0.05) -> str:
        console = Console()

        console.rule(":robot_face:")
        chat_history = [(None, self.initial_message)]
        console.print("[green]" + self.initial_message + "[/green]")
        done = False
        while not done:
            user_input = Prompt.ask("", console=console)
            with Live(console=console) as live:
                completion = ""
                for x in self.complete(user_input, chat_history):
                    if x is not None:
                        completion += x
                        time.sleep(delay)
                    if self.end_token in completion:
                        done = True
                        completion = completion.replace(self.end_token, "")
                    live.update("[green]" + completion + "[/green]")
            chat_history.append((user_input, completion))
        console.rule(":robot_face:")

        # TODO: Create a better transcript
        transcript = "\n\n".join(
            ["\n".join([str(x[0]), str(x[1])]) for x in chat_history]
        )
        return transcript


class AzureOpenAISearch:
    """
    A class that encapsulates the Azure OpenAI and Azure Search functionalities (semantic search and RAG: retrieved-augmented generation).

    TO DO: combine with the Client class.
    """

    @staticmethod
    def survey_id_to_index_name(survey_id: str) -> str:
        """
        Convert a qualtrics survey id to an Azure Search index name
        Index name must only contain lowercase letters, digits or dashes,
        cannot start or end with dashes and is limited to 128 characters.
        """
        index_name = survey_id.lower().replace("_", "-")[:128]
        logger.debug(f"Converted {survey_id=} to {index_name=}")
        return index_name

    def __init__(self, index_name):
        self.openai_client = Client()

        self.index_name = index_name
        self.search_index = SearchIndex(
            name=self.index_name,
            fields=[
                SearchField(name="id", type=SearchFieldDataType.String, key=True),
                SearchField(name="content", type=SearchFieldDataType.String),
            ],
        )

        self.admin_key = os.getenv("AZURE_OPENAI_SEARCH_KEY")
        self.credential = AzureKeyCredential(self.admin_key)

        self.azure_search_service_endpoint = os.getenv("AZURE_OPENAI_SEARCH_ENDPOINT")
        self.search_index_client = SearchIndexClient(
            endpoint=self.azure_search_service_endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )
        self.search_client = SearchClient(
            endpoint=self.azure_search_service_endpoint,
            index_name=self.index_name,
            credential=self.credential,
        )

    def upload(self, documents: list[str]):
        """
        Upload documents to the Azure Search database
        """
        self.search_index_client.create_or_update_index(self.search_index)

        # Upload your list of strings to the index
        docs = [
            {"id": str(i), "content": content} for i, content in enumerate(documents)
        ]
        self.search_client.upload_documents(docs)

    def rag(self, query: str):
        extra_body = {
            "data_sources": [
                {
                    "type": "azure_search",
                    "parameters": {
                        "endpoint": self.azure_search_service_endpoint,
                        "index_name": self.index_name,
                        "authentication": {
                            "type": "api_key",
                            "key": self.admin_key,
                        },
                    },
                }
            ],
        }
        gen = self.openai_client.complete(
            user_input=query, chat_history=[], stream=False, extra_body=extra_body
        )
        # We get a generator with a single response back - consume it and return to caller
        result = list(gen)[0]

        return result

    def delete_index(self):
        logger.info(f"Deleting index {self.index_name}")
        self.search_index_client.delete_index(self.search_index)


@cache
def get_client(
    missing_ok=True,
    initial_message="",
    system_message="",
    temperature=0.7,
    end_token="<end_of_chat>",
):
    try:
        client = Client(
            initial_message=initial_message,
            system_message=system_message,
            temperature=temperature,
            end_token=end_token,
        )
    except ValueError:
        if not missing_ok:
            raise
        return None
    else:
        return client
