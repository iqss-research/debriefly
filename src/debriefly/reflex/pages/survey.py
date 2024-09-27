import reflex as rx
import reflex_clerk as clerk
from sqlmodel import select
from reflex.utils.serializers import serializer
from debriefly.reflex.templates import template
from debriefly.reflex.backend.models import Question, Answer
from debriefly.qualtrics import (
    QualtricsRequest,
    QualtricsQuestion,
)


@serializer
def serialize_qualtricsrequest(value: QualtricsRequest) -> str:
    from reflex.utils import format

    return format.json_dumps({"dataa": value.data})


@serializer
def serialize_qualtricsquestion(value: QualtricsQuestion) -> str:
    from reflex.utils import format

    return format.json_dumps({value.question_id: value.question_text})


class SurveyState(rx.State):

    survey_id: str = ""
    questions: list[str] = []
    current_question: int = 0
    total_questions: int = 0
    answers: list[str] = []
    current_answer: str = ""
    debriefing_answer_id: int

    def load_survey(self, survey_id):
        self.survey_id = survey_id
        with rx.session() as session:
            question = session.exec(
                select(Question).where(Question.id == survey_id)
            ).first()
            if question is not None:
                self.current_question = 0
                self.questions = [question.question_text]
                self.total_questions = len(self.questions)
                self.answers = [""] * self.total_questions

    def on_load(self):
        self.load_survey(self.router.page.params.get("s_id"))

    async def submit(self):
        state = await self.get_state(clerk.ClerkState)
        user_id = state.user_id
        with rx.session() as session:
            answer = Answer(
                user_id=user_id, question_id=self.survey_id, answer=self.answers[0]
            )
            session.add(answer)
            session.commit()
            self.debriefing_answer_id = answer.id

    async def next_question(self):
        self.answers[self.current_question] = self.current_answer
        self.current_answer = ""
        if self.current_question < self.total_questions - 1:
            self.current_question += 1
        else:
            await self.submit()
            return rx.redirect(f"/chat/{self.debriefing_answer_id}")


@template(route="/survey/[s_id]", title="Survey", on_load=SurveyState.on_load)
def survey() -> rx.Component:
    return rx.vstack(
        rx.heading(f"Survey {SurveyState.survey_id}"),
        rx.text(SurveyState.questions[SurveyState.current_question]),
        rx.text_area(
            on_change=SurveyState.set_current_answer,
            value=SurveyState.current_answer,
            width="100%",
            rows="10",
        ),
        rx.button(
            rx.cond(
                SurveyState.current_question == SurveyState.total_questions - 1,
                "Submit",
                "Next",
            ),
            color_scheme="grass",
            on_click=lambda: SurveyState.next_question(),
        ),
        width="100%",
    )


@template(route="/survey_chat/[s_id]", title="Survey Chat")
def survey_chat() -> rx.Component:
    return rx.vstack(
        rx.text(f"Survey Chat {SurveyState.survey_id}"),
    )
