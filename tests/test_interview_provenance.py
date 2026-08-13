from types import SimpleNamespace

from debriefly.interview_provenance import (
    merge_model_version,
    prompt_version,
    snapshot_interview,
)
from debriefly.openai import Client
from debriefly.reflex.form_designer.pages.response import interview_configuration


def test_prompt_version_is_stable_and_changes_with_either_prompt():
    version = prompt_version("system", "initial")

    assert version == prompt_version("system", "initial")
    assert version.startswith("sha256:")
    assert len(version) == len("sha256:") + 64
    assert version != prompt_version("changed system", "initial")
    assert version != prompt_version("system", "changed initial")


def test_merge_model_version_preserves_order_without_duplicates():
    versions = merge_model_version("", "gpt-4o-mini-2024-07-18")
    versions = merge_model_version(versions, "gpt-4o-mini-2024-07-18")
    versions = merge_model_version(versions, "gpt-4o-mini-2026-01-01")

    assert versions == "gpt-4o-mini-2024-07-18, gpt-4o-mini-2026-01-01"
    assert merge_model_version(versions, None) == versions


def test_snapshot_records_the_exact_effective_prompts_without_api_key():
    client = Client(
        api_key="secret-test-key",
        api_model="gpt-test-alias",
        system_message="Rendered system prompt",
        initial_message="Rendered initial message",
    )
    record = SimpleNamespace()

    snapshot_interview(record, client)

    assert record.interview_model == "gpt-test-alias"
    assert record.interview_system_prompt == client.system_message
    assert record.interview_system_prompt.endswith(
        "Include the special <end_of_chat> token in the response to end the chat."
    )
    assert record.interview_initial_prompt == "Rendered initial message"
    assert record.interview_prompt_version == prompt_version(
        record.interview_system_prompt,
        record.interview_initial_prompt,
    )
    assert "secret-test-key" not in vars(record).values()


def test_client_can_reuse_an_effective_prompt_without_appending_again():
    effective_prompt = (
        "Rendered system prompt\n"
        "Include the special <end_of_chat> token in the response to end the chat."
    )

    client = Client(
        api_key="secret-test-key",
        api_model="gpt-test-alias",
        system_message=effective_prompt,
        append_end_token_instruction=False,
    )

    assert client.system_message == effective_prompt


def test_results_configuration_renders_models_version_and_exact_prompts():
    component = interview_configuration(
        "gpt-test-alias",
        "gpt-test-2026-08-12",
        "sha256:abc123",
        "Exact system prompt",
        "Exact initial message",
    )
    rendered = str(component)

    for expected in (
        "Interview configuration",
        "Configured model:",
        "gpt-test-alias",
        "API-reported model version:",
        "gpt-test-2026-08-12",
        "Prompt fingerprint:",
        "sha256:abc123",
        "Exact system prompt",
        "Exact initial message",
    ):
        assert expected in rendered

    # Accordion content otherwise inherits the accent color, which can render
    # white text on the prompt snapshot's light neutral background.
    assert '"color": "var(--gray-12)"' in rendered


def test_results_configuration_explains_legacy_interviews():
    rendered = str(interview_configuration("", "", "", "", ""))

    assert "Configuration unavailable" in rendered
