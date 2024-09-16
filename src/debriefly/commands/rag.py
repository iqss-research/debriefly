import logging
import tempfile
import json
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey
from debriefly.openai import AzureOpenAISearch

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument(
        "--index_name", type=str, required=True, help="Name of the Azure Search index."
    )  # to do: remove it
    parser.add_argument(
        "--keyword", type=str, required=True, help="Keywords or Queries for search."
    )
    parser.add_argument(
        "--upload_search",
        type=bool,
        default=True,
        help="Whether to upload the search results to Azure search. Make it False if you uploaded already.",
    )
    return parser


def rag(survey_id, index_name, keyword, upload_search=True):

    client = AzureOpenAISearch(index_name=index_name)

    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with tempfile.NamedTemporaryFile() as f:
            logger.info("Collecting responses")
            survey.collect_responses(f.name, compress=False)
            content = json.loads(open(f.name, "r").read())
            transcripts = [r["values"]["debriefly"] for r in content]

            if upload_search:
                try:
                    client.upload(documents=transcripts)
                except Exception as e:
                    logger.error(f"Error uploading documents: {e}")
            client.rag(query=keyword)


def main(args):
    rag(
        survey_id=args.survey_id,
        index_name=args.index_name,
        keyword=args.keyword,
        upload_search=args.upload_search,
    )
