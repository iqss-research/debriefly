import os
from dotenv import load_dotenv
from debriefly.qualtrics import QualtricsSession


load_dotenv()

session = QualtricsSession(survey_id="SV_8ADyHCnFttPUPJA")
ui = session.get_ui()

kwargs = {}
username = os.getenv("GRADIO_USERNAME")
password = os.getenv("GRADIO_PASSWORD")
if username is not None and password is not None:
    kwargs = {"auth": (username, password)}

ui.launch(**kwargs)
