import logging
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey


logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument(
        "--output_file", type=str, required=True, help="Path to the saved zip file."
    )
    return parser


def collect(survey_id, output_file):
    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        survey.collect_responses(output_file)


def main(args):
    collect(survey_id=args.survey_id, output_file=args.output_file)
