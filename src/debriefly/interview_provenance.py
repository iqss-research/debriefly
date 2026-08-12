"""Utilities for recording the exact setup used by an LLM interview."""

import hashlib
import json


def prompt_version(system_prompt: str, initial_prompt: str) -> str:
    """Return a stable identifier for an exact pair of rendered prompts."""
    payload = json.dumps(
        {
            "initial_prompt": initial_prompt,
            "system_prompt": system_prompt,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def merge_model_version(existing: str, model_version: str | None) -> str:
    """Add a model version to a comma-separated, insertion-ordered set."""
    version = (model_version or "").strip()
    if not version:
        return existing

    versions = [item.strip() for item in existing.split(",") if item.strip()]
    if version not in versions:
        versions.append(version)
    return ", ".join(versions)


def snapshot_interview(record, client) -> None:
    """Attach an immutable client/prompt snapshot to an interview record."""
    record.interview_model = client.model
    record.interview_system_prompt = client.system_message
    record.interview_initial_prompt = client.initial_message
    record.interview_prompt_version = prompt_version(
        client.system_message,
        client.initial_message,
    )
