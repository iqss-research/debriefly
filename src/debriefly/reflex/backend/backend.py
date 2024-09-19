import reflex as rx
from sqlmodel import select, asc, desc, or_, func
import logging
import reflex_clerk as clerk
from debriefly.reflex.backend.models import Config, Question, Answer, Profile
from debriefly.qualtrics import QualtricsSession, QualtricsSurveyCreator


logger = logging.getLogger(__name__)


class State(clerk.ClerkState):
    current_question: Question = Question()
    questions: list[Question] = []
    search_value: str = ""
    sort_value: str = ""
    sort_reverse: bool = False

    profile: Profile = Profile()
    config: dict[str, str] = {}

    def load_config(self):
        with rx.session() as session:
            for config in session.exec(select(Config)):
                self.config[config.name] = config.value

    def load_entries(self) -> list[Question]:
        with rx.session() as session:
            query = select(Question).where(Question.user_id == self.user_id)
            if self.search_value:
                search_value = f"%{str(self.search_value).lower()}%"
                query = query.where(
                    or_(
                        *[
                            getattr(Question, field).ilike(search_value)
                            for field in Question.get_fields()
                            if not field.endswith("id")
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

    def load_profile(self):
        logger.info("Loading Profile")
        if self.user_id is not None:
            with rx.session() as session:
                profile = session.exec(
                    select(Profile).where(Profile.user_id == self.user_id)
                ).first()
                if profile is None:
                    logger.info(f"Saving profile for user {self.user_id}")
                    profile = Profile(user_id=self.user_id)
                    session.add(profile)
                    session.commit()
                    self.profile = session.exec(
                        select(Profile).where(Profile.user_id == self.user_id)
                    ).first()
                else:
                    self.profile = profile

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
            question = Question(user_id=self.user_id, **self.current_question)
            session.add(question)
            session.commit()
        self.load_entries()
        return rx.toast.info("Question has been added.")

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
            f"Question {self.current_question['id']} has been modified."
        )

    def delete_question(self, id: int):
        with rx.session() as session:
            question = session.exec(select(Question).where(Question.id == id)).first()
            session.delete(question)
            session.commit()
        self.load_entries()
        return rx.toast.info(f"Question {question.id} has been deleted.")

    def download_question(self, id: int):
        csv_data = "id,question_text\n0,foo"
        return rx.download(data=csv_data, filename=f"data_{id}.csv")

    def update_profile(self, form_data: dict):
        for field in Profile.get_fields():
            if field != "id" and field in form_data:
                setattr(self.profile, field, form_data[field])
        with rx.session() as session:
            session.add(self.profile)
            session.commit()
            self.load_profile()
        return rx.toast.success("Profile updated successfully")

    def create_qualtrics_survey(self, question: Question):
        with QualtricsSession(
            data_center=self.profile.qualtrics_data_center,
            api_token=self.profile.qualtrics_api_token,
            client_id=self.profile.qualtrics_client_id,
            client_secret=self.profile.qualtrics_client_secret,
        ):
            survey = QualtricsSurveyCreator().create_survey(
                name="auto00", question_text=question["question_text"]
            )

            return rx.toast.success(
                f"Survey {survey.survey_id} created", position="top-center"
            )


class AnswerState(rx.State):
    # TODO: Inherit from clerk.ClerkState; filter by user_id as well
    question_id: int
    answers: list[Answer] = []
    search_value: str = ""
    sort_value: str = ""
    sort_reverse: bool = False

    def load_entries(self) -> list[Answer]:
        self.question_id = self.router.page.params.get("question_id")
        with rx.session() as session:
            query = select(Answer).where(Answer.question_id == self.question_id)
            if self.search_value:
                search_value = f"%{str(self.search_value).lower()}%"
                query = query.where(
                    or_(
                        *[
                            getattr(Answer, field).ilike(search_value)
                            for field in Answer.get_fields()
                            if not field.endswith("id")
                        ],
                    )
                )

            if self.sort_value:
                sort_column = getattr(Answer, self.sort_value)
                if self.sort_value == "id":
                    order = desc(sort_column) if self.sort_reverse else asc(sort_column)
                else:
                    order = (
                        desc(func.lower(sort_column))
                        if self.sort_reverse
                        else asc(func.lower(sort_column))
                    )
                query = query.order_by(order)

            self.answers = session.exec(query).all()

    def sort_values(self, sort_value: str):
        self.sort_value = sort_value
        self.load_entries()

    def toggle_sort(self):
        self.sort_reverse = not self.sort_reverse
        self.load_entries()

    def filter_values(self, search_value):
        self.search_value = search_value
        self.load_entries()

    def delete_answer(self, id: int):
        with rx.session() as session:
            answer = session.exec(select(Answer).where(Answer.id == id)).first()
            session.delete(answer)
            session.commit()
        self.load_entries()
        return rx.toast.info(f"Answer {answer.id} has been deleted.")
