#!/usr/bin/env python3
"""Export the existing Reflex pages with the request-stream Lambda transport.

Run from any directory with the application's pinned dependencies installed:
    .venv/bin/python serverless/build_frontend.py

The result is serverless/dist/. This command only builds local files; it does
not upload assets, invoke AWS, or change the existing application deployment.
"""

from __future__ import annotations

import argparse
from importlib.metadata import version
import os
from pathlib import Path
import re
import shutil
import sys
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
TRANSPORT = Path(__file__).resolve().parent / "frontend" / "request_transport.mjs"
SOCKET_IMPORT = 'import io from "socket.io-client";'
STREAM_IMPORT = 'import io from "/utils/request_transport.mjs";'


def install_transport(web_directory: Path) -> None:
    """Patch only the generated transport import, failing on runtime changes."""
    state_path = web_directory / "utils" / "state.js"
    original = state_path.read_text()
    if original.count(SOCKET_IMPORT) == 1:
        original = original.replace(SOCKET_IMPORT, STREAM_IMPORT)
    elif original.count(STREAM_IMPORT) != 1:
        raise RuntimeError(
            "The generated Reflex transport changed. Review request_transport.mjs "
            "against the pinned Reflex runtime before exporting."
        )
    shutil.copyfile(TRANSPORT, state_path.parent / TRANSPORT.name)
    state_path.write_text(original)
    # Native HTML login/logout forms bypass Reflex's backend URL helper. Keep
    # those paths on the same origin even when compiling with local dev settings.
    for generated in [
        *web_directory.joinpath("pages").rglob("*.js"),
        web_directory / "utils" / "stateful_components.js",
    ]:
        if generated.is_file():
            source = generated.read_text()
            updated = re.sub(r'https?://[^\s\'"`{}]+(?=/_event/auth/)', "", source)
            if updated != source:
                generated.write_text(updated)


def build(output_directory: Path, *, skip_install: bool = False) -> None:
    if version("reflex") != "0.5.10":
        raise RuntimeError("This transport is tested with reflex==0.5.10.")
    os.chdir(PROJECT)
    sys.path.insert(0, str(PROJECT))
    sys.path.insert(0, str(PROJECT / "src"))
    os.environ["DEBRIEFLY_LAMBDA"] = "true"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["REFLEX_ENV_MODE"] = "prod"
    os.environ["REFLEX_TELEMETRY_ENABLED"] = "false"
    os.environ["NEXT_TELEMETRY_DISABLED"] = "1"

    from debriefly.serverless.build_info import capture_build_info, write_build_info

    build_info = capture_build_info(PROJECT)

    from reflex import constants
    from reflex.config import get_config
    from reflex.utils import build as reflex_build
    from reflex.utils import export as reflex_export
    from reflex.utils import prerequisites

    # Absolute localhost URLs in generated helpers resolve to the browser origin
    # through Reflex's own getBackendURL(). Authentication forms use relative
    # /_event/auth paths, and the new transport uses relative /_lambda/event.
    config = get_config()
    config.api_url = "http://localhost"
    if prerequisites.needs_reinit(frontend=True):
        prerequisites.initialize_frontend_dependencies()
    original_setup = reflex_build.setup_frontend

    def setup_and_patch(*args, **kwargs):
        original_setup(*args, **kwargs)
        install_transport(Path(prerequisites.get_web_dir()))

    # The official export flow compiles Python pages first. Install the shim
    # after that compile and before Next builds; compilation cannot overwrite it.
    with patch.object(reflex_build, "setup_frontend", setup_and_patch):
        if skip_install:
            if not (
                Path(prerequisites.get_web_dir()) / "node_modules" / "next"
            ).is_dir():
                raise RuntimeError(
                    "--skip-install requires existing frontend dependencies in .web/node_modules."
                )
            with patch.object(prerequisites, "install_frontend_packages"):
                reflex_export.export(frontend=True, backend=False, zipping=False)
        else:
            reflex_export.export(frontend=True, backend=False, zipping=False)

    static_directory = Path(prerequisites.get_web_dir()) / constants.Dirs.STATIC
    if not (static_directory / "index.html").is_file():
        raise RuntimeError("Reflex did not produce the expected static frontend.")
    output_directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(static_directory, output_directory, dirs_exist_ok=True)
    write_build_info(output_directory, build_info)
    print(f"Static frontend ready for review: {output_directory}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "serverless" / "dist")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Use the existing .web/node_modules; compile all pages without downloading packages.",
    )
    parser.add_argument(
        "--patch-only",
        type=Path,
        metavar="WEB_DIRECTORY",
        help="Install the transport into an already generated .web tree without rebuilding.",
    )
    args = parser.parse_args()
    if args.patch_only is not None:
        install_transport(args.patch_only.resolve())
    else:
        build(args.output.resolve(), skip_install=args.skip_install)


if __name__ == "__main__":
    main()
