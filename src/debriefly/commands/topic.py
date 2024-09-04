import logging
import tempfile
import json
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey
#for topic modeling
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument(
        "--output_file", type=str, required=True, help="Path to the saved csv file."
    )
    return parser


def do_topic(transcripts: list, output_file: str):
    '''
    function to implement the topic modeling with BERTopic

    Inputs:
    - transcripts: list of strings, each string is a transcript
    - output_file: str, the path to save the output (output is currently a topic list)

    '''
    logger.info("Fitting topic model with BERTopic...")

    #fitting topic model
    representation_model = KeyBERTInspired()
    topic_model = BERTopic(n_gram_range=(1, 3), min_topic_size=3, representation_model=representation_model)
    topics, _ = topic_model.fit_transform(transcripts)

    topic_model.get_topic_info().to_csv(output_file, index=False)


def topic(survey_id, output_file):
    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with tempfile.NamedTemporaryFile() as f:
            logger.info("Collecting responses")
            survey.collect_responses(f.name, compress=False)
            content = json.loads(open(f.name, "r").read())
            transcripts = [r["values"]["debriefly"] for r in content]

            do_topic(transcripts, output_file=output_file)


def main(args):
    topic(
        survey_id=args.survey_id,
        output_file=args.output_file,
    )
