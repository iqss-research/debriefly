import os
from openai import OpenAI
from debriefly.qualtrics import (
    QualtricsSession,
    QualtricsSurvey,
    QualtricsSurveySession,
)
import logging

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    return parser


def run(survey_id):
    if os.getenv("OPENAI_API_KEY") is not None:
        openai_client = OpenAI(
            organization=os.getenv("OPENAI_ORG_ID"),
            project=os.getenv("OPENAI_PROJECT_ID"),
        )
    else:
        openai_client = None

    with QualtricsSession(openai_client=openai_client):
        survey = QualtricsSurvey(survey_id=survey_id)
        survey_session = QualtricsSurveySession(survey=survey)
        survey_session.run()


def main(args):
    run(survey_id=args.survey_id)
