import reflex as rx
import logging
import openai
from debriefly.openai import get_client
from debriefly.reflex.backend.models import QualtricsEmbedSession, UserOpenAISettings
from debriefly.reflex.form_designer.pages.response import ResponsesState

logger = logging.getLogger(__name__)


def qualtrics_debriefing_context_chunks(
    embed_sessions: list[QualtricsEmbedSession],
    debriefings: dict[str, list[dict[str, str]]],
) -> list[str]:
    chunks = []
    for embed_session in embed_sessions:
        messages = debriefings.get(embed_session.public_id, [])
        if not messages:
            continue

        transcript = "\n".join(
            f"{message['role']}: {message['content']}" for message in messages
        )
        metadata = [
            f"Question: {embed_session.question_text}",
            f"Answer: {embed_session.response_text}",
        ]
        if embed_session.external_response_id:
            metadata.insert(
                0, f"Qualtrics Response ID: {embed_session.external_response_id}"
            )
        if embed_session.external_question_id:
            metadata.insert(
                0, f"Qualtrics Question ID: {embed_session.external_question_id}"
            )

        chunks.append(
            f"Qualtrics Interview {embed_session.public_id}:\n"
            + "\n".join(metadata)
            + f"\n\n{transcript}"
        )
    return chunks


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
        # Rebuild private context from a freshly authorized form before using
        # the form owner's API key or contacting OpenAI.
        self.load_responses()
        if not self._user_has_access():
            self.processing = False
            yield rx.toast.error("Survey not found.")
            return
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

        chunks.extend(
            qualtrics_debriefing_context_chunks(
                self.qualtrics_embed_sessions,
                self.qualtrics_debriefings,
            )
        )

        return "\n\n---\n\n".join(chunks)
