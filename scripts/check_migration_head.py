"""Verify that the committed Alembic revision graph has one expected head."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


def _assignment(module: ast.Module, name: str, path: Path):
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue
        if any(
            isinstance(target, ast.Name) and target.id == name for target in targets
        ):
            try:
                return ast.literal_eval(statement.value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}: {name} must be a literal") from exc
    raise ValueError(f"{path}: missing {name}")


def migration_heads(versions_directory: Path) -> set[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(versions_directory.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _assignment(module, "revision", path)
        down_revision = _assignment(module, "down_revision", path)
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{path}: revision must be a non-empty string")
        if revision in revisions:
            raise ValueError(f"duplicate Alembic revision: {revision}")
        revisions.add(revision)
        if isinstance(down_revision, str):
            parents.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            if not all(isinstance(parent, str) for parent in down_revision):
                raise ValueError(f"{path}: down_revision contains a non-string")
            parents.update(down_revision)
        elif down_revision is not None:
            raise ValueError(f"{path}: unsupported down_revision value")
    if not revisions:
        raise ValueError(f"No Alembic revisions found in {versions_directory}")
    missing_parents = parents - revisions
    if missing_parents:
        raise ValueError(
            f"Alembic revisions have missing parents: {sorted(missing_parents)!r}"
        )
    return revisions - parents


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: check_migration_head.py <expected-revision>", file=sys.stderr)
        return 2
    expected = arguments[0]
    versions_directory = Path(__file__).resolve().parents[1] / "alembic/versions"
    try:
        heads = migration_heads(versions_directory)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"Could not validate Alembic revisions: {exc}", file=sys.stderr)
        return 1
    if heads != {expected}:
        print(
            f"Expected the sole Alembic head {expected!r}, found {sorted(heads)!r}",
            file=sys.stderr,
        )
        return 1
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
