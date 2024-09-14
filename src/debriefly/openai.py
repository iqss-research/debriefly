import os
from functools import cache
import logging
from rich.console import Console
from rich.prompt import Prompt
from rich.live import Live
import time
from openai import OpenAI, AzureOpenAI

#functionalities added
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex, SearchField, SearchFieldDataType
import csv
import numpy as np

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

    def complete(self, user_input, chat_history):
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
            stream=True,
        )

        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

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
    '''
    A class that encapsulates the Azure OpenAI and Azure Search functionalities (semantic search and RAG: retrieved-augmented generation).

    TO DO: combine with the Client class.
    '''
    def __init__(self, index_name):
        self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.admin_key = os.getenv("AZURE_OPENAI_SEARCH_KEY")
        self.azure_search_service_endpoint = os.getenv("AZURE_OPENAI_SEARCH_ENDPOINT")
        self.index_name = index_name

        self.openai_client = AzureOpenAI(
            azure_endpoint= self.azure_endpoint,
            api_key= self.api_key,
            api_version="2024-02-01"
        )
        self.credential = AzureKeyCredential(self.admin_key)
        self.search_client = SearchClient(endpoint = self.azure_search_service_endpoint, index_name= self.index_name, credential= self.credential)
        self.search_index_client = SearchIndexClient(endpoint= self.azure_search_service_endpoint, index_name = self.index_name, credential= self.credential)

    def upload(self, documents: list[str]):
        '''
        upload documents to the Azure Search database
        '''
        # Define an index
        fields = [
            SearchField(name="id", type=SearchFieldDataType.String, key=True),
            SearchField(name="content", type=SearchFieldDataType.String)
        ]
        index = SearchIndex(name=self.index_name, fields=fields)
        self.search_index_client.create_index(index)

        # Upload your list of strings to the index
        docs = [{"id": str(i), "content": content} for i, content in enumerate(documents)]
        self.search_client.upload_documents(docs)
    ########################
    # Following methods are commented out as they are not currently in use.
    ########################
    #def get_embeddings(self, documents: list[str]) -> list[list[float]]:
    #    '''
    #    Get the embedding of the documents
    #
    #    Inputs:
    #    - documents: list of strings, each string is a document
    #
    #    Outputs:
    #    - embedding_list: list of embeddings
    #    '''
    #    embedding_list = []
    #    for doc in documents:
    #        response = self.openai_client.embeddings.create(input=doc, model="text-embedding-3-small")  # Make sure to use the correct embedding model
    #        embedding_list.append(response.data[0].embedding)
    #    return embedding_list
    #
    #def search(self, query: str, documents: list[str], output_file: str):
    #    '''
    #    Search the transcripts based on the query. Output the results to a CSV file.
    #
    #    Inputs:
    #    - documents: list of strings, each string is a document
    #    - query: str, the query to search for
    #    - output_file: str, the path to save the output
    #
    #    '''
    #    #obtain the embedding for the query
    #    query_embed = self.get_embeddings([query])
    #    embeddings = self.get_embeddings(documents)
    #
    #    #calculate cosine-similarity
    #    embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    #    query_embed_norm = query_embed / np.linalg.norm(query_embed)
    #    cosine_similarities = np.dot(embeddings_norm, query_embed_norm.T).reshape(-1)
    #
    #    #sort the transcripts according to the cosine-similarity
    #    valid_indices = [index for index in np.argsort(-cosine_similarities) if index < len(documents)]
    #    result_list = [(documents[i], cosine_similarities[i]) for i in valid_indices]
    #
    #    #write csv file
    #    with open(output_file, "w") as csvfile:
    #        csv_writer = csv.writer(csvfile)
    #        csv_writer.writerow(["Transcript", "Cosine Similarity"])
    #        for result in result_list:
    #            csv_writer.writerow(result)
    #
    def rag(self, query: str):
        '''
        Retrieve and generate response based on the query
        '''
        # Get embeddings for the query
        completion = self.openai_client.chat.completions.create(
            model= os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL"),
            messages=[
                {
                    "role": "user",
                    "content": query,
                },
            ],
            extra_body={
                "data_sources":[
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": self.azure_search_service_endpoint,
                            "index_name": self.index_name,
                        "authentication": {
                            "type": "api_key",
                            "key":  self.admin_key,
                                },
                            }
                        }
                    ],
                },
            )
        result = completion.choices[0].message.content
        print(result)


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
