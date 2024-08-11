import os
from dotenv import load_dotenv
from openai import OpenAI
from debriefly.qualtrics import (
    QualtricsSession,
    QualtricsSurvey,
    QualtricsSurveySession,
)


if __name__ == "__main__":
    load_dotenv()

    openai_client = OpenAI(
        organization=os.environ["OPENAI_ORG_ID"],
        project=os.environ["OPENAI_PROJECT_ID"],
    )

    with QualtricsSession(openai_client=openai_client):
        survey = QualtricsSurvey(survey_id="SV_8ADyHCnFttPUPJA")
        survey_session = QualtricsSurveySession(survey=survey)

        survey_session.run()
