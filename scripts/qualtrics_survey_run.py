from dotenv import load_dotenv
from debriefly.qualtrics import (
    QualtricsSurvey,
    QualtricsSurveySession,
)
from debriefly.openai import get_client

if __name__ == "__main__":
    load_dotenv()

    openai_client = get_client()

    survey = QualtricsSurvey(survey_id="SV_1ELMxREKi1ZleYu")
    print(survey)
    survey_session = QualtricsSurveySession(survey=survey)

    survey_session.run()
