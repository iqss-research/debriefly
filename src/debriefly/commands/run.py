import logging
from debriefly.qualtrics import (
    QualtricsSession,
    QualtricsSurvey,
    QualtricsSurveySession,
)
from debriefly.openai import get_client


logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    return parser


def run(survey_id):
    openai_client = get_client()

    with QualtricsSession(openai_client=openai_client):
        survey = QualtricsSurvey(survey_id=survey_id)
        survey_session = QualtricsSurveySession(survey=survey)
        survey_session.run()


def main(args):
    run(survey_id=args.survey_id)
