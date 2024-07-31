from dotenv import load_dotenv
from debriefly.qualtrics import QualtricsSession


if __name__ == "__main__":

    load_dotenv()

    session = QualtricsSession(survey_id="SV_8ADyHCnFttPUPJA")
    session.run_terminal()
