import reflex as rx
import logging
import openai
from debriefly.openai import get_client
from debriefly.reflex.backend.models import UserOpenAISettings
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

        context = self.debriefing_context()
        if not context:
            self.chat[-1].answer = "No debriefing chat transcripts are available."
            self.processing = False
            yield
            return

        with rx.session() as session:
            settings = UserOpenAISettings.get_for_user(session, self.form.user_id)
            if settings is None or not settings.is_configured:
                self.chat[-1].answer = "Add your OpenAI API key before using analysis."
                self.processing = False
                yield
                return
            api_key = settings.api_key
            api_model = settings.model

        client = get_client(
            missing_ok=False,
            api_key=api_key,
            api_model=api_model,
            system_message=(
                "You analyze cognitive debriefing survey transcripts. "
                "Answer using only the transcript context provided by the system. "
                "If the context is insufficient, say so."
            ),
            end_token="",
        )

        messages = [
            {
                "role": "system",
                "content": f"{client.system_message}\n\nTranscript context:\n{context}",
            }
        ]
        for qa in self.chat[:-1]:
            messages.append({"role": "user", "content": qa.question})
            messages.append({"role": "assistant", "content": qa.answer})

        messages.append({"role": "user", "content": question})

        try:
            session = client.client.chat.completions.create(
                model=client.model,
                messages=messages,
                temperature=client.temperature,
                stream=True,
            )
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            self.chat[-1].answer = "The analysis could not contact OpenAI."
            self.processing = False
            yield
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

        # Toggle the processing flag.
        self.processing = False

    def debriefing_context(self) -> str:
        chunks = []
        for response in self.responses:
            response_chunks = []
            for field in self.form.fields:
                messages = self.response_debriefings.get(response.id, {}).get(
                    field.id, []
                )
                if not messages:
                    continue

                transcript = "\n".join(
                    f"{message['role']}: {message['content']}" for message in messages
                )
                response_chunks.append(f"Field {field.name}:\n{transcript}")

            if response_chunks:
                chunks.append(
                    f"Response {response.client_token}:\n"
                    + "\n\n".join(response_chunks)
                )

        return "\n\n---\n\n".join(chunks)
