import os
from dotenv import load_dotenv
from openai import OpenAI
from debriefly.qualtrics import QualtricsSurvey


if __name__ == "__main__":
    load_dotenv()

    client = OpenAI(
        organization=os.environ["OPENAI_ORG_ID"],
        project=os.environ["OPENAI_PROJECT_ID"],
    )

    survey = QualtricsSurvey(survey_id="SV_8ADyHCnFttPUPJA")
    selected_question = survey.get_debriefing_question(client=client)
    print(selected_question)
