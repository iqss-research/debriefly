import time
import logging
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey
from debriefly.openai import AzureOpenAISearch

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument("--query", type=str, required=True, help="Query for search.")
    parser.add_argument(
        "--wait-time",
        type=int,
        default=20,
        help="Wait time in seconds before searching the index. Default %(default)s",
    )
    parser.add_argument(
        "--auto-delete",
        action="store_true",
        help="Auto delete the created Azure OpenAI Index after the search.",
    )
    return parser


def analyze(survey_id, query, auto_delete=False, wait_time=20):

    index_name = AzureOpenAISearch.survey_id_to_index_name(survey_id)
    client = AzureOpenAISearch(index_name=index_name)

    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with survey.transcripts() as transcripts:
            client.upload(documents=transcripts)

            logger.info(f"Waiting for {wait_time} seconds before searching the index.")
            time.sleep(wait_time)

            result = client.rag(query=query)
            print(result)
            if auto_delete:
                client.delete_index()


def main(args):
    analyze(
        survey_id=args.survey_id,
        query=args.query,
        auto_delete=args.auto_delete,
        wait_time=args.wait_time,
    )
