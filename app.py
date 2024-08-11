import os
from dotenv import load_dotenv
from openai import OpenAI
from debriefly.qualtrics import QualtricsSession, QualtricsSurveySession


load_dotenv()

openai_client = OpenAI(
    organization=os.environ["OPENAI_ORG_ID"],
    project=os.environ["OPENAI_PROJECT_ID"],
)

with QualtricsSession():
    session = QualtricsSurveySession(
        survey_id=None,  # "SV_8ADyHCnFttPUPJA",
        openai_client=openai_client,
        debriefing_question="QID6",
    )
    ui = session.get_ui()

    kwargs = {}
    username = os.getenv("GRADIO_USERNAME")
    password = os.getenv("GRADIO_PASSWORD")
    if username is not None and password is not None:
        kwargs = {"auth": (username, password)}

    ui.launch(**kwargs)
