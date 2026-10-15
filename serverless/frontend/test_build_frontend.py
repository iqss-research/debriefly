"""Guard the very small, version-specific generated frontend change."""

import importlib.util
from pathlib import Path
import shlex

import pytest


SPEC = importlib.util.spec_from_file_location(
    "lambda_build_frontend", Path(__file__).resolve().parents[1] / "build_frontend.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

BUILD_INFO_SPEC = importlib.util.spec_from_file_location(
    "lambda_build_info",
    Path(__file__).resolve().parents[2] / "src/debriefly/serverless/build_info.py",
)
build_info = importlib.util.module_from_spec(BUILD_INFO_SPEC)
BUILD_INFO_SPEC.loader.exec_module(build_info)


@pytest.fixture
def source_project(tmp_path):
    project = tmp_path / "project"
    source = project / "src/debriefly"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text(
        '__version__ = "1.0.0"\nraise AssertionError("Must not import application")\n'
    )
    (source / "component.py").write_text('label = "original"\n')
    (project / "assets").mkdir()
    (project / "assets/logo.svg").write_text("<svg>original</svg>")
    return project


def test_transport_patch_keeps_generated_view_and_uses_same_origin_auth(tmp_path):
    (tmp_path / "utils").mkdir()
    (tmp_path / "pages").mkdir()
    runtime = tmp_path / "utils" / "state.js"
    source = '// generated runtime\nimport io from "socket.io-client";\nconst layout = "original";\n'
    runtime.write_text(source)
    page = tmp_path / "pages" / "signin.js"
    page.write_text(
        "<form action={`http://localhost:8000/_event/auth/login`}>Original UI</form>"
    )

    builder.install_transport(tmp_path)

    assert runtime.read_text() == source.replace(
        builder.SOCKET_IMPORT, builder.STREAM_IMPORT
    )
    assert page.read_text() == "<form action={`/_event/auth/login`}>Original UI</form>"
    assert (
        tmp_path / "utils" / "request_transport.mjs"
    ).read_bytes() == builder.TRANSPORT.read_bytes()
    builder.install_transport(tmp_path)
    assert runtime.read_text().count(builder.STREAM_IMPORT) == 1


def test_fails_closed_if_reflex_changes_the_transport_import(tmp_path):
    (tmp_path / "utils").mkdir()
    runtime = tmp_path / "utils" / "state.js"
    source = "import { io } from 'new-transport';\n"
    runtime.write_text(source)
    with pytest.raises(RuntimeError, match="transport changed"):
        builder.install_transport(tmp_path)
    assert runtime.read_text() == source
    assert not (tmp_path / "utils" / "request_transport.mjs").exists()


def test_export_warns_after_version_change_and_preserves_prebuild_snapshot(
    tmp_path, source_project
):
    output = tmp_path / "custom export with spaces"
    output.mkdir()
    snapshot = build_info.capture_build_info(source_project)
    build_info.write_build_info(output, snapshot)
    assert build_info.frontend_warning(output, source_project) is None

    version_file = source_project / "src/debriefly/__init__.py"
    version_file.write_text(version_file.read_text().replace('"1.0.0"', '"1.1.0"'))
    # A source edit during compilation must not become part of its build metadata.
    build_info.write_build_info(output, snapshot)
    warning = build_info.frontend_warning(output, source_project)
    assert "built version: 1.0.0" in warning
    assert "source version: 1.1.0" in warning
    command = next(
        line.strip() for line in warning.splitlines() if ".venv/bin/python" in line
    )
    arguments = shlex.split(command)
    assert arguments[:3] == [
        ".venv/bin/python",
        "serverless/build_frontend.py",
        "--skip-install",
    ]
    assert arguments[3:] == ["--output", str(output)]

    (output / build_info.MANIFEST_NAME).write_text("[")
    assert "no valid build information" in build_info.frontend_warning(
        output, source_project
    )


@pytest.mark.parametrize(
    "changed_file", ["src/debriefly/component.py", "assets/logo.svg"]
)
def test_export_ignores_local_artifacts_but_detects_source_and_asset_edits(
    tmp_path, source_project, changed_file
):
    output = tmp_path / "export"
    output.mkdir()
    build_info.write_build_info(output, build_info.capture_build_info(source_project))
    for name in (
        ".env",
        "src/debriefly/.env",
        "src/debriefly/review.db",
        "src/debriefly/review.sqlite3",
        "src/debriefly/__pycache__/component.pyc",
        "src/debriefly/.web/generated.js",
        "src/debriefly/dist/index.html",
        "src/debriefly/cache/generated.json",
    ):
        artifact = source_project / name
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("local runtime artifact")
    assert build_info.frontend_warning(output, source_project) is None

    target = source_project / changed_file
    target.write_text(target.read_text().replace("original", "modified"))
    assert "out of date" in build_info.frontend_warning(output, source_project)
