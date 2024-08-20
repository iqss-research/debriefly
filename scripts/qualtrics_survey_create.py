from dotenv import load_dotenv
from debriefly.qualtrics import QualtricsSession, QualtricsSurveyCreator


if __name__ == "__main__":
    load_dotenv()

    with QualtricsSession():
        survey = QualtricsSurveyCreator().create_survey(
            name="Hello", question_text="How're you feeling today?"
        )
        print(survey.id)
