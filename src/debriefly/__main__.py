import logging
import argparse
import os
from dotenv import load_dotenv

import debriefly
from debriefly.commands import create, run

logger = logging.getLogger("debriefly")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=debriefly.__version__)

    modules = (
        create,
        run,
    )

    subparsers = parser.add_subparsers(title="Choose a command")
    subparsers.required = True

    def get_str_name(module):
        return os.path.splitext(os.path.basename(module.__file__))[0]

    for module in modules:
        this_parser = subparsers.add_parser(
            get_str_name(module), description=module.__doc__
        )
        this_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Increase verbosity"
        )
        module.add_args(this_parser)
        this_parser.set_defaults(func=module.main)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    logger.info(f"Debriefly v{debriefly.__version__}")

    args.func(args)


if __name__ == "__main__":
    main()
