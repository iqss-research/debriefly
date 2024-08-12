import json
from pathlib import Path
import pytest
from debriefly.qualtrics import QualtricsSurvey


@pytest.fixture
def qualtrics_survey():
    # A Survey created from a local json file mirroring what we'll
    # get from the Qualtrics REST API
    survey1_json = Path(__file__).parent / "survey1.json"
    survey1_data = json.loads(survey1_json.read_text())
    # Create a QualtricsSurvey by providing data directly; no API calls made
    return QualtricsSurvey(data=survey1_data)


def test_survey_n_questions(qualtrics_survey):
    assert len(qualtrics_survey.questions) == 4


def test_survey_question_mc(qualtrics_survey):
    question = qualtrics_survey.questions["QID4"]
    assert question.question_id == "QID4"
    assert question.question_text == "Which of the following is a prime number?"
    # display text to internal code
    assert question.choices == {"2": "1", "4": "2", "6": "3"}


def test_survey_question_te(qualtrics_survey):
    question = qualtrics_survey.questions["QID6"]
    assert question.question_id == "QID6"
    assert question.question_text == "What is the meaning of life?"
