import logging
import tempfile
import json
import csv
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey


logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument(
        "--output_file", type=str, required=True, help="Path to the saved csv file."
    )
    return parser


def do_analysis(transcripts, output_file):
    logger.info("Analyzing transcripts")
    with open(output_file, "w") as csvfile:
        csv_writer = csv.writer(csvfile)

        counts = [len(transcript) for transcript in transcripts]
        csv_writer.writerow(counts)


def analyze(survey_id, output_file):
    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with tempfile.NamedTemporaryFile() as f:
            logger.info("Collecting responses")
            survey.collect_responses(f.name, compress=False)
            content = json.loads(open(f.name, "r").read())
            transcripts = [r["values"]["debriefly"] for r in content]

            do_analysis(transcripts, output_file)


def main(args):
    analyze(survey_id=args.survey_id, output_file=args.output_file)
