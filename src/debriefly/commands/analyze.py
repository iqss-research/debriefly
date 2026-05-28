import logging
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey
from debriefly.openai import get_client

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument("--query", type=str, required=True, help="Query for search.")
    parser.add_argument(
        "--wait-time",
        type=int,
        default=20,
        help="Deprecated legacy Azure index wait time. Ignored.",
    )
    parser.add_argument(
        "--auto-delete",
        action="store_true",
        help="Deprecated legacy Azure index cleanup flag. Ignored.",
    )
    return parser


def analyze(survey_id, query, auto_delete=False, wait_time=20):

    client = get_client(missing_ok=False, end_token="")

    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with survey.transcripts() as transcripts:
            context = "\n\n---\n\n".join(
                f"Response {response_id}:\n{transcript}"
                for response_id, transcript in transcripts.items()
            )

    response = client.client.chat.completions.create(
        model=client.model,
        temperature=client.temperature,
        stream=False,
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze cognitive debriefing survey transcripts. "
                    "Answer using only the transcript context provided."
                ),
            },
            {
                "role": "user",
                "content": f"Transcript context:\n{context}\n\nQuestion:\n{query}",
            },
        ],
    )
    print(response.choices[0].message.content)


def main(args):
    analyze(
        survey_id=args.survey_id,
        query=args.query,
        auto_delete=args.auto_delete,
        wait_time=args.wait_time,
    )
