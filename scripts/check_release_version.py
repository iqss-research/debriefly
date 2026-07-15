"""Check that a release tag matches Debriefly's package and runtime versions."""

from __future__ import annotations

from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = (
    (PROJECT_ROOT / "pyproject.toml", r'^version = "([^"]+)"$'),
    (PROJECT_ROOT / "src/debriefly/__init__.py", r'^__version__ = "([^"]+)"$'),
)


def release_versions() -> list[str]:
    versions: list[str] = []
    for path, pattern in VERSION_FILES:
        match = re.search(
            pattern,
            path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        if match is None:
            raise ValueError(f"Could not find the release version in {path}")
        versions.append(match.group(1))
    return versions


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: check_release_version.py <release-tag>", file=sys.stderr)
        return 2
    expected = arguments[0]
    try:
        versions = release_versions()
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    if versions != [expected, expected]:
        print(
            f"Tag {expected!r} does not match application versions {versions!r}",
            file=sys.stderr,
        )
        return 1
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
