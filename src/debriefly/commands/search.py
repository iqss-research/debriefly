import logging
import csv
import numpy as np
from debriefly.qualtrics import QualtricsSession, QualtricsSurvey
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument("--survey_id", type=str, required=True)
    parser.add_argument("--query", type=str, required=True, help="Query for search.")
    parser.add_argument(
        "--output_file", type=str, required=True, help="Path to the saved csv file."
    )
    return parser


def do_search(transcripts: list, output_file: str, query: str):
    """
    function to implement the semantic search by keywords

    Inputs:
    - transcripts: list of strings, each string is a transcript
    - output_file: str, the path to save the output
    - query: str, the query to search for
    """

    logger.info("Searching transcripts")

    with open(output_file, "w") as csvfile:
        csv_writer = csv.writer(csvfile)

        # loading sentence transformer model
        # (TO DO: make the model selection. Currently, use the lightest model)
        model = SentenceTransformer(
            "multi-qa-mpnet-base-cos-v1"
        )  # you can change the model
        embeddings = model.encode(transcripts)

        # embed keyword / query
        query_embed = model.encode(query)

        # calculate cosine-similarity
        embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        query_embed_norm = query_embed / np.linalg.norm(query_embed)
        cosine_similarities = np.dot(embeddings_norm, query_embed_norm)

        # sort the transcripts according to the cosine-similarity
        valid_indices = [
            index
            for index in np.argsort(-cosine_similarities)
            if index < len(transcripts)
        ]
        result_list = [(transcripts[i], cosine_similarities[i]) for i in valid_indices]

        csv_writer.writerow(["Transcript", "Cosine Similarity"])
        for result in result_list:
            csv_writer.writerow(result)


def search(survey_id, output_file, query):
    with QualtricsSession():
        survey = QualtricsSurvey(survey_id=survey_id)
        with survey.transcripts() as transcripts:
            do_search(transcripts, output_file=output_file, query=query)


def main(args):
    search(
        survey_id=args.survey_id,
        output_file=args.output_file,
        query=args.query,
    )
