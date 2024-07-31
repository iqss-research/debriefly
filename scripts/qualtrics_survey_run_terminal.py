import os
from dotenv import load_dotenv
from openai import OpenAI
from debriefly.qualtrics import QualtricsSession


if __name__ == "__main__":

    load_dotenv()

    client = OpenAI(
        organization=os.environ["OPENAI_ORG_ID"],
        project=os.environ["OPENAI_PROJECT_ID"],
    )

    session = QualtricsSession(survey_id="SV_8ADyHCnFttPUPJA", openapi_client=client)
    session.run_terminal()
