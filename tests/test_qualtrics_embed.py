import asyncio
import importlib
import json

import pytest
import reflex as rx

from debriefly.reflex.backend.models import (
    Form,
    QualtricsEmbedSession,
    User,
    UserOpenAISettings,
)
from debriefly.reflex.components.analyze.state import (
    qualtrics_debriefing_context_chunks,
)
from debriefly.reflex.form_designer.pages.response import transcript_messages
from debriefly.reflex.pages.qualtrics_embed import QualtricsEmbedState
from sqlmodel import Session, SQLModel, create_engine, select


qualtrics_embed_module = importlib.import_module(
    "debriefly.reflex.pages.qualtrics_embed"
)


@pytest.fixture
def embed_engine(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qualtrics-embed.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(
        qualtrics_embed_module.rx,
        "session",
        lambda: Session(engine),
    )
    return engine


def test_form_delete_cascades_qualtrics_embed_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="abc123", user_id=user.user_id)
        form.qualtrics_embed_sessions.append(
            QualtricsEmbedSession(
                question_text="How clear was this question?",
                response_text="Very clear",
            )
        )
        session.add(user)
        session.add(form)
        session.commit()

        saved_form = session.exec(select(Form).where(Form.code == "abc123")).one()
        session.delete(saved_form)
        session.commit()

        assert session.exec(select(QualtricsEmbedSession)).all() == []


def test_transcript_messages_returns_clean_message_dicts():
    raw_transcript = json.dumps(
        [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "I chose yes."},
            {"role": "", "content": "ignored"},
            {"role": "assistant", "content": ""},
            "ignored",
        ]
    )

    assert transcript_messages(raw_transcript) == [
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "I chose yes."},
    ]


def test_analysis_context_includes_qualtrics_embed_transcripts():
    embed_session = QualtricsEmbedSession(
        form_id=1,
        public_id="embed-123",
        external_response_id="R_abc",
        external_question_id="QID1",
        question_text="How clear was this question?",
        response_text="Very clear",
    )

    context = "\n\n---\n\n".join(
        qualtrics_debriefing_context_chunks(
            [embed_session],
            {
                "embed-123": [
                    {"role": "assistant", "content": "What did clear mean to you?"},
                    {"role": "user", "content": "It was easy to understand."},
                ]
            },
        )
    )

    assert "Qualtrics Interview embed-123" in context
    assert "Qualtrics Response ID: R_abc" in context
    assert "Qualtrics Question ID: QID1" in context
    assert "Question: How clear was this question?" in context
    assert "Answer: Very clear" in context
    assert "user: It was easy to understand." in context


def test_qualtrics_embed_snapshots_and_reuses_model_and_prompts(embed_engine):
    with Session(embed_engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="abc123", user_id=user.user_id)
        settings = UserOpenAISettings(
            user_id=user.user_id,
            api_key="secret-test-key",
            model="gpt-test-alias",
        )
        session.add_all([user, form, settings])
        session.commit()

    async def load_embed(params):
        root = rx.State(_reflex_internal_init=True)
        state = await root.get_state(QualtricsEmbedState)
        state.router.page.params.update(params)
        await QualtricsEmbedState.on_load.fn(state)
        return state

    first_state = asyncio.run(
        load_embed(
            {
                "form_code": "abc123",
                "question": "How clear was this question?",
                "response": "Very clear",
                "qid": "QID1",
                "response_id": "R_abc",
            }
        )
    )
    first_state._record_api_model_version("gpt-test-2026-08-12")

    with Session(embed_engine) as session:
        record = session.exec(select(QualtricsEmbedSession)).one()
        session_id = record.public_id
        original_system_prompt = record.interview_system_prompt
        original_initial_prompt = record.interview_initial_prompt
        original_prompt_version = record.interview_prompt_version
        assert record.interview_model == "gpt-test-alias"
        assert record.interview_model_versions == "gpt-test-2026-08-12"
        assert "How clear was this question?" in original_initial_prompt
        assert "Very clear" in original_initial_prompt
        assert original_system_prompt.endswith(
            "Include the special <end_of_chat> token in the response to end the chat."
        )

        settings = session.get(UserOpenAISettings, "owner")
        settings.model = "gpt-changed-alias"
        session.add(settings)
        session.commit()

    second_state = asyncio.run(
        load_embed(
            {
                "form_code": "abc123",
                "question": "Changed question",
                "response": "Changed answer",
                "session_id": session_id,
            }
        )
    )

    with Session(embed_engine) as session:
        unchanged = session.exec(select(QualtricsEmbedSession)).one()
        assert unchanged.question_text == "How clear was this question?"
        assert unchanged.response_text == "Very clear"
        assert unchanged.external_question_id == "QID1"
        assert unchanged.external_response_id == "R_abc"
        assert unchanged.interview_model == "gpt-test-alias"
        assert unchanged.interview_system_prompt == original_system_prompt
        assert unchanged.interview_initial_prompt == original_initial_prompt
        assert unchanged.interview_prompt_version == original_prompt_version

    assert first_state.configured_model == "gpt-test-alias"
    assert second_state.configured_model == "gpt-test-alias"
    assert second_state.api_reported_model_versions == "gpt-test-2026-08-12"
    assert second_state.system_message == original_system_prompt
    assert second_state.initial_message == original_initial_prompt


def test_legacy_qualtrics_interview_cannot_mix_in_current_configuration(
    embed_engine,
):
    with Session(embed_engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="abc123", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()
        session.add(
            UserOpenAISettings(
                user_id=user.user_id,
                api_key="secret-test-key",
                model="current-model-must-not-be-used",
            )
        )
        record = QualtricsEmbedSession(
            form_id=form.id,
            public_id="legacy-session",
            question_text="Legacy question",
            response_text="Legacy answer",
            transcript=json.dumps([{"role": "assistant", "content": "Legacy opening"}]),
            completed=False,
        )
        session.add(record)
        session.commit()

    async def load_embed():
        root = rx.State(_reflex_internal_init=True)
        state = await root.get_state(QualtricsEmbedState)
        state.router.page.params.update(
            {
                "form_code": "abc123",
                "question": "Legacy question",
                "response": "Legacy answer",
                "session_id": "legacy-session",
            }
        )
        await QualtricsEmbedState.on_load.fn(state)
        return state

    state = asyncio.run(load_embed())

    with Session(embed_engine) as session:
        unchanged = session.exec(select(QualtricsEmbedSession)).one()
        assert unchanged.interview_model == ""
        assert unchanged.interview_prompt_version == ""
        assert unchanged.interview_system_prompt == ""
        assert unchanged.interview_initial_prompt == ""

    assert "cannot be resumed" in state.error
