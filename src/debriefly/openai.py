import os
import logging
from rich.console import Console
from rich.prompt import Prompt
from rich.live import Live
import time
from openai import OpenAI

from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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
        api_key=None,
        api_version=None,
        api_endpoint=None,
        api_model=None,
        initial_message="",
        system_message="",
        temperature=0.7,
        end_token="<end_of_chat>",
        append_end_token_instruction=True,
    ):

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        api_model = api_model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

        if not api_key:
            raise ValueError("OpenAI API key is required.")

        self.client = self.model = None
        self.initial_message = initial_message
        self.temperature = temperature
        self.end_token = end_token

        self.system_message = system_message
        if self.end_token and append_end_token_instruction:
            self.system_message += f"\nInclude the special {self.end_token} token in the response to end the chat."

        logger.debug("Instantiating OpenAI client")
        self.client = OpenAI(
            api_key=api_key,
        )
        self.model = api_model

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


def get_client(
    missing_ok=True,
    initial_message="",
    system_message="",
    temperature=0.7,
    end_token="<end_of_chat>",
    api_key=None,
    api_version=None,
    api_endpoint=None,
    api_model=None,
    append_end_token_instruction=True,
):
    try:
        client = Client(
            api_key=api_key,
            api_version=api_version,
            api_endpoint=api_endpoint,
            api_model=api_model,
            append_end_token_instruction=append_end_token_instruction,
            initial_message=initial_message,
            system_message=system_message,
            temperature=temperature,
            end_token=end_token,
        )
    except:  # noqa: E722
        if not missing_ok:
            raise
        return None
    else:
        return client


class PromptVerdict(str, Enum):
    OK = "ok"  # prompt is narrowly about survey wording
    REJECT = "reject"  # disallowed, refuse to save


def check_prompt_compliance(
    text: str,
    *,
    api_key: str | None = None,
    api_version: str | None = None,
    api_endpoint: str | None = None,
    api_model: str | None = None,
) -> PromptVerdict:

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OpenAI API key is required.")

    client = OpenAI(api_key=key)
    model = api_model or os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL

    system = (
        "You are a policy checker for a *cognitive-debriefing* survey tool.\n"
        "A prompt is **OK** when it sets up an interview whose primary purpose"
        "is to understand how respondents interpret a survey question (a.k.a. cognitive debriefing). "
        "A prompt is **REJECT** only if it clearly tries to reuse the LLM for something unrelated "
        "to survey-question validation (e.g., writing code, political persuasion, marketing copy) "
        "or contains disallowed content.\n"
        "Return one word only:\n"
        "  'ok'      – prompt focuses on improving survey wording\n"
        "  'reject'  – clearly tries to use the LLM for something else or violates policy"
    )

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        stream=False,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    )
    verdict = resp.choices[0].message.content.strip().lower()
    try:
        return PromptVerdict(verdict)
    except ValueError:
        return PromptVerdict.REJECT
