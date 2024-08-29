import logging
from debriefly.openai import get_client


logger = logging.getLogger(__name__)


def add_args(parser):
    parser.add_argument(
        "--initial-message",
        type=str,
        default="Hello! I'm here to chat.",
        help="The initial message to start the conversation. Default (%(default)s)",
    )
    parser.add_argument(
        "--system-message",
        type=str,
        default="",
        help="System message for the bot. Default (%(default)s)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="The temperature of the model. Default (%(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="The delay between individual chunks of messages from server. Default (%(default)s",
    )
    parser.add_argument("--end-token", type=str, default="<end_of_chat>")
    return parser


def chat(args):
    client = get_client(
        initial_message=args.initial_message,
        system_message=args.system_message,
        temperature=args.temperature,
        end_token=args.end_token,
    )
    client.interactive_chat(delay=args.delay)


def main(args):
    chat(args)
