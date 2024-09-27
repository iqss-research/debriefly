import logging
from rich.console import Console

from debriefly.qualtrics.request import QualtricsRequest
from debriefly.qualtrics.question import QualtricsQuestionFactory

logger = logging.getLogger(__name__)


class QualtricsSurveySession(QualtricsRequest):
    def __init__(self, survey, data=None):
        self.method = "post"
        self.endpoint = f"surveys/{survey.survey_id}/sessions"

        super().__init__(data)

        self.session_id = self.data["sessionId"]
        self.survey = survey
        self.process()

    def __str__(self):
        return f"Session {self.session_id} for {self.survey}"

    def submit(self, answers=None, embedded_data=None):
        # If no answers are provided (just embedded_data),
        # or if we're done, we don't advance the survey.
        json = {"advance": answers is not None and not self.done}
        answers = answers or {}
        json["responses"] = answers
        if embedded_data is not None:
            json["embeddedData"] = {"debriefly": str(embedded_data)}

        self.make_request(url=self.session_id, json=json)
        if not self.done:
            self.process()

    def process(self):
        self.questions = {}
        for q in self.data["questions"]:
            # Note: The dictionary format we get here is different from the
            # survey api, hence the massaging of dictionaries etc.
            choices = q.get("choices", {})
            choices = {c["choiceId"]: {"choiceText": c["display"]} for c in choices}
            question = QualtricsQuestionFactory(
                survey=self.survey,
                question_type=q["type"],
                question_id=q["questionId"],
                question_dict={"questionText": q["display"], "choices": choices},
            )
            self.questions[question.question_id] = question
        self.done = self.data["done"]

    def run(self):
        _ = self.survey.debriefing_question  # access to populate

        console = Console()
        console.rule(f"Survey {self.survey.survey_id}")
        while not self.done:
            answers = {}
            for question in self.questions.values():
                answer = question.prompt(console)
                answers |= answer

                debriefing_q = self.survey.debriefing_question
                if (
                    debriefing_q is not None
                    and debriefing_q.question.question_id in answers
                ):
                    logger.debug(
                        f"Debriefing Question: {debriefing_q} found in answers. Saving response."
                    )
                    debriefing_q.response = answers[debriefing_q.question.question_id]

                if self.survey.last_question.question_id in self.questions:
                    if debriefing_q := self.survey.debriefing_question:
                        logger.debug("Starting debriefing")
                        transcript = debriefing_q.prompt(console)
                        self.submit(answers, embedded_data=transcript)

            if not self.done:
                self.submit(answers)

        console.print(self.done)
