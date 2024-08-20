from debriefly.qualtrics import (
    QualtricsSession,
    QualtricsSurveyCreator,
)
import logging

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--name", type=str, help="Name of the survey", required=True)
    parser.add_argument(
        "--question_text", type=str, help="Text Question for the survey", required=True
    )
    return parser


def create(name, question_text):
    with QualtricsSession():
        survey = QualtricsSurveyCreator().create_survey(
            name=name, question_text=question_text
        )
        logger.info(f"Survey created with id {survey.survey_id}")


def main(args):
    create(name=args.name, question_text=args.question_text)
