import os
import openai

import reflex as rx
from sqlmodel import select, asc, desc, or_, func

from .models import Question

_client = None


def get_openai_client():
    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


class State(rx.State):
    """The app state."""

    current_question: Question = Question()
    questions: list[Question] = []
    search_value: str = ""
    sort_value: str = ""
    sort_reverse: bool = False
    tone: str = "😊 Formal"
    length: str = "300"
    chat_content_data: str = "Click 'Analyze' to generate OpenAI's view on a question."
    gen_response = False

    def load_entries(self) -> list[Question]:
        with rx.session() as session:
            query = select(Question)
            if self.search_value:
                search_value = f"%{str(self.search_value).lower()}%"
                query = query.where(
                    or_(
                        *[
                            getattr(Question, field).ilike(search_value)
                            for field in Question.get_fields()
                            if field != "id"
                        ],
                    )
                )

            if self.sort_value:
                sort_column = getattr(Question, self.sort_value)
                if self.sort_value == "id":
                    order = desc(sort_column) if self.sort_reverse else asc(sort_column)
                else:
                    order = (
                        desc(func.lower(sort_column))
                        if self.sort_reverse
                        else asc(func.lower(sort_column))
                    )
                query = query.order_by(order)

            self.questions = session.exec(query).all()

    def sort_values(self, sort_value: str):
        self.sort_value = sort_value
        self.load_entries()

    def toggle_sort(self):
        self.sort_reverse = not self.sort_reverse
        self.load_entries()

    def filter_values(self, search_value):
        self.search_value = search_value
        self.load_entries()

    def get_question(self, question: Question):
        self.current_question = question

    def add_question_to_db(self, form_data: dict):
        self.current_question = form_data

        with rx.session() as session:
            session.add(Question(**self.current_question))
            session.commit()
        self.load_entries()
        return rx.toast.info(
            "Question has been added.", variant="outline", position="bottom-right"
        )

    def update_question_to_db(self, form_data: dict):
        self.current_question.update(form_data)
        with rx.session() as session:
            question = session.exec(
                select(Question).where(Question.id == self.current_question["id"])
            ).first()
            for field in Question.get_fields():
                if field != "id":
                    setattr(question, field, self.current_question[field])
            session.add(question)
            session.commit()
        self.load_entries()
        return rx.toast.info(
            f"Question {self.current_question['id']} has been modified.",
            variant="outline",
            position="bottom-right",
        )

    def delete_question(self, id: int):
        with rx.session() as session:
            question = session.exec(select(Question).where(Question.id == id)).first()
            session.delete(question)
            session.commit()
        self.load_entries()
        return rx.toast.info(
            f"Question {question.id} has been deleted.",
            variant="outline",
            position="bottom-right",
        )

    @rx.background
    async def call_openai(self):
        session = get_openai_client().chat.completions.create(
            user=self.router.session.client_token,
            stream=True,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": f"You are a chatbot that answers all question in a maximum of {self.length} characters.",
                },
                {
                    "role": "user",
                    "content": f"What do you think of the following as a survey question: {self.current_question.question_text}",
                },
            ],
        )
        for item in session:
            if hasattr(item.choices[0].delta, "content"):
                response_text = item.choices[0].delta.content
                async with self:
                    if response_text is not None:
                        self.chat_content_data += response_text
                yield

        async with self:
            self.gen_response = False

    def analyze(self, question: Question):
        self.current_question = Question(**question)
        self.gen_response = True
        self.chat_content_data = ""
        return State.call_openai
