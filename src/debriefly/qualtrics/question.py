from logging import getLogger
from rich.prompt import Prompt

logger = getLogger(__name__)


class QualtricsQuestionFactory:
    def __new__(cls, survey, question_type, question_id, question_dict):
        question_type = question_type.lower()
        if question_type == "mc":
            return QualtricsQuestionMC(survey, question_id, question_dict)
        elif question_type == "te":
            return QualtricsQuestionText(survey, question_id, question_dict)
        else:
            raise ValueError(f"Unsupported question type: {question_type}")


class QualtricsQuestion:
    def __init__(self, survey, question_id, question_dict):
        self.survey = survey
        self.question_id = question_id
        self.question_text = question_dict["questionText"]

    def prompt(self, console):
        raise NotImplementedError


class QualtricsQuestionText(QualtricsQuestion):
    def __str__(self):
        return f"{self.question_id}: {self.question_text}"

    def prompt(self, console):
        answer = Prompt.ask(self.question_text)
        return {self.question_id: answer}


class QualtricsQuestionMC(QualtricsQuestion):
    def __init__(self, survey, question_id, question_dict):
        super().__init__(survey, question_id, question_dict)
        choices = {
            v["choiceText"]: k for k, v in question_dict.get("choices", {}).items()
        }
        self.choices = choices

    def __str__(self):
        choices = "/".join(self.choices.keys())
        return f"{self.question_id}: {self.question_text} ({choices})"

    def prompt(self, console):
        while True:
            answer = Prompt.ask(
                f"{self.question_text}", choices=list(self.choices.keys())
            )
            if answer in self.choices:
                break
            else:
                console.print("[red]Invalid choice.[/red]")
        return {self.question_id: {self.choices[answer]: {"selected": True}}}


class QualtricsQuestionDebriefing(QualtricsQuestion):
    end_of_survey_token = "<end_of_survey>"

    def __init__(self, survey, question, response):
        self.survey = survey
        self.question = question
        self.response = response

    def prompt(self, console) -> str:
        self.survey.populate_system_message(
            question=self.question, response=self.response
        )
        chat_history = [(None, self.survey.initial_message)]
        while True:
            last_message = chat_history[-1][1]
            console.print(last_message, style="bold cyan")
            user_input = Prompt.ask("", console=console)
            completion = self.survey.chat(user_input, chat_history)
            chat_history.append((user_input, completion))

            if self.end_of_survey_token in completion:
                break

        # TODO: Create a better transcript
        transcript = "\n\n".join(
            ["\n".join([str(x[0]), str(x[1])]) for x in chat_history]
        )

        return transcript
