import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _required_match(pattern: str, path: Path) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, f"Could not find a version in {path}"
    return match.group(1)


def test_package_and_runtime_versions_match():
    package_version = _required_match(
        r'^version = "([^"]+)"$',
        ROOT / "pyproject.toml",
    )
    runtime_version = _required_match(
        r'^__version__ = "([^"]+)"$',
        ROOT / "src/debriefly/__init__.py",
    )

    assert package_version == runtime_version


def test_release_version_check_accepts_the_candidate_version():
    version = _required_match(
        r'^version = "([^"]+)"$',
        ROOT / "pyproject.toml",
    )
    result = subprocess.run(
        [sys.executable, "scripts/check_release_version.py", version],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_release_version_check_rejects_a_mismatched_tag():
    version = _required_match(
        r'^version = "([^"]+)"$',
        ROOT / "pyproject.toml",
    )
    result = subprocess.run(
        [sys.executable, "scripts/check_release_version.py", f"{version}-wrong"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "does not match" in result.stderr
