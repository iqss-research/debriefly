"""Track which local application sources produced a static frontend export."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex


PROJECT = Path(__file__).resolve().parents[3]
MANIFEST_NAME = ".debriefly-build.json"
SCHEMA_VERSION = 1
SOURCE_DIRECTORIES = ("src/debriefly", "assets")
SOURCE_FILES = (
    "pyproject.toml",
    "requirements.txt",
    "rxconfig.py",
    "serverless/build_frontend.py",
    "serverless/frontend/request_transport.mjs",
)
EXCLUDED_DIRECTORIES = {
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "cache",
}
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def application_version(project: Path = PROJECT) -> str:
    """Read the source version without importing application dependencies."""
    source = project / "src/debriefly/__init__.py"
    for statement in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        ):
            if isinstance(statement.value, ast.Constant) and isinstance(
                statement.value.value, str
            ):
                return statement.value.value
    raise ValueError(f"No literal __version__ found in {source}")


def source_fingerprint(project: Path = PROJECT) -> str:
    """Hash explicit source/configuration inputs, excluding local runtime files."""
    sources = {project / name for name in SOURCE_FILES}
    for name in SOURCE_DIRECTORIES:
        directory = project / name
        for source in directory.rglob("*"):
            parts = source.relative_to(directory).parts
            if (
                source.is_file()
                and not any(
                    part.startswith(".")
                    or part in EXCLUDED_DIRECTORIES
                    or part.endswith(".egg-info")
                    for part in parts
                )
                and source.suffix not in DATABASE_SUFFIXES | {".pyc", ".pyo"}
            ):
                sources.add(source)
    digest = hashlib.sha256()
    for source in sorted(sources):
        if source.is_file():
            digest.update(source.relative_to(project).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(source.read_bytes()).digest())
    return digest.hexdigest()


def capture_build_info(project: Path = PROJECT) -> dict:
    """Capture inputs before compilation, so edits during a build stay visible."""
    return {
        "schema_version": SCHEMA_VERSION,
        "application_version": application_version(project),
        "source_fingerprint": source_fingerprint(project),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def write_build_info(directory: Path, build_info: dict) -> None:
    """Write metadata only after a successful frontend export."""
    (directory / MANIFEST_NAME).write_text(
        json.dumps(build_info, indent=2) + "\n", encoding="utf-8"
    )


def frontend_warning(directory: Path, project: Path = PROJECT) -> str | None:
    """Explain missing/stale build metadata without changing the local export."""
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        reason = "The exported frontend has no valid build information and may be out of date."
    else:
        try:
            current = capture_build_info(project)
        except (OSError, SyntaxError, ValueError) as error:
            return f"Cannot check frontend freshness against the local source: {error}"
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != SCHEMA_VERSION
        ):
            reason = "The exported frontend has unsupported build information and may be out of date."
        elif (
            manifest.get("source_fingerprint") == current["source_fingerprint"]
            and manifest.get("application_version") == current["application_version"]
        ):
            return None
        else:
            reason = (
                "The exported frontend is out of date "
                f"(built version: {manifest.get('application_version', 'unknown')}; "
                f"source version: {current['application_version']})."
            )
    command = ".venv/bin/python serverless/build_frontend.py --skip-install"
    if directory.resolve() != (project / "serverless/dist").resolve():
        command += f" --output {shlex.quote(str(directory.resolve()))}"
    return (
        f"{reason}\nRebuild locally from {project}:\n  {command}\n"
        "Then refresh the browser. Restart the preview if backend code also changed."
    )
