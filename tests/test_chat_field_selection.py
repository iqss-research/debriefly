import asyncio

import pytest
import reflex as rx
from sqlmodel import Session, SQLModel, create_engine, select

import debriefly.reflex.components.chat.state as chat_state_module
from debriefly.reflex.backend.models import Form, Response, User
from debriefly.reflex.backend.models import (
    Field,
    FieldType,
    FieldValue,
    UserOpenAISettings,
)
from debriefly.reflex.components.chat.state import (
    ChatState,
    QA,
    _debriefing_field_id_for_chat,
)
from debriefly.reflex.form_designer.pages.form_entry import (
    FormEntryState,
    FormEntryTabState,
)


def make_field(id_: int, *, debriefing: bool = False) -> Field:
    field = Field(
        form_id=1,
        name=f"field_{id_}",
        type_=FieldType.text,
        debriefing=debriefing,
        ordering=float(id_),
    )
    field.id = id_
    return field


def test_chat_selects_the_exact_submitted_debriefing_field():
    assert (
        _debriefing_field_id_for_chat(
            [make_field(10, debriefing=True), make_field(11)], 10
        )
        == 10
    )


def test_chat_rejects_a_submitted_field_that_is_not_for_debriefing():
    assert _debriefing_field_id_for_chat([make_field(10), make_field(11)], 10) is None


def test_chat_rejects_a_submitted_field_that_is_not_on_the_active_page():
    assert (
        _debriefing_field_id_for_chat(
            [make_field(10, debriefing=True), make_field(11)], 12
        )
        is None
    )


def test_chat_rejects_a_missing_submitted_field_id():
    assert _debriefing_field_id_for_chat([make_field(10, debriefing=True)], -1) is None


@pytest.fixture
def chat_engine(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat-state.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(chat_state_module.rx, "session", lambda: Session(engine))
    return engine


def test_missing_field_value_clears_previous_chat_state(chat_engine):
    with Session(chat_engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()
        field = Field(
            form_id=form.id,
            name="question",
            type_=FieldType.text,
            debriefing=True,
            ordering=1.0,
        )
        response = Response(client_token="respondent", form_id=form.id)
        session.add_all([field, response])
        session.commit()
        session.refresh(form)
        session.refresh(field)

    async def load_chat():
        root = rx.State(_reflex_internal_init=True)
        entry_state = await root.get_state(FormEntryState)
        tab_state = await root.get_state(FormEntryTabState)
        chat_state = await root.get_state(ChatState)

        entry_state.client_token = "respondent"
        entry_state.form = form
        entry_state.pending_debriefing_field_id = field.id
        tab_state.active_tab = 0
        tab_state.fields = [[field]]

        chat_state.loaded = True
        chat_state.chat = [QA(question="old question", answer="old answer")]
        chat_state.field_value_id = 999

        await ChatState.on_load.fn(chat_state)
        return chat_state

    state = asyncio.run(load_chat())

    assert state.loaded
    assert state.chat == []
    assert state.field_value_id == -1
    assert "could not be loaded" in state.error


def test_chat_snapshots_and_reuses_exact_model_and_prompts(chat_engine):
    with Session(chat_engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()
        session.add(
            UserOpenAISettings(
                user_id=user.user_id,
                api_key="secret-test-key",
                model="gpt-test-alias",
            )
        )
        field = Field(
            form_id=form.id,
            name="question",
            type_=FieldType.text,
            debriefing=True,
            prompt="How clear was the question?",
            custom_system_message=(
                "System for {{ question }} / {{ response }} / "
                "{{ end_of_survey_token }}"
            ),
            custom_initial_message="Opening for {{ response }}",
            min_debriefing_time=0,
            max_debriefing_time=0,
            ordering=1.0,
        )
        response = Response(client_token="respondent", form_id=form.id)
        session.add_all([field, response])
        session.flush()
        field_value = FieldValue(
            field_id=field.id,
            response_id=response.id,
            value="Very clear",
        )
        session.add(field_value)
        session.flush()
        form_id = form.id
        field_id = field.id
        field_value_id = field_value.id
        session.commit()

    async def load_chat():
        with Session(chat_engine) as session:
            loaded_form = session.get(Form, form_id)
            loaded_field = session.get(Field, field_id)

        root = rx.State(_reflex_internal_init=True)
        entry_state = await root.get_state(FormEntryState)
        tab_state = await root.get_state(FormEntryTabState)
        chat_state = await root.get_state(ChatState)
        entry_state.client_token = "respondent"
        entry_state.form = loaded_form
        entry_state.pending_debriefing_field_id = field_id
        tab_state.active_tab = 0
        tab_state.fields = [[loaded_field]]

        await ChatState.on_load.fn(chat_state)
        return chat_state

    first_state = asyncio.run(load_chat())
    first_state._record_api_model_version("gpt-test-2026-08-12")

    with Session(chat_engine) as session:
        snapshot = session.get(FieldValue, field_value_id)
        assert snapshot.interview_model == "gpt-test-alias"
        assert snapshot.interview_model_versions == "gpt-test-2026-08-12"
        assert snapshot.interview_initial_prompt == "Opening for Very clear"
        assert snapshot.interview_system_prompt.startswith(
            "System for How clear was the question? / Very clear / "
            "&lt;end_of_chat&gt;"
        )
        assert snapshot.interview_system_prompt.endswith(
            "Include the special <end_of_chat> token in the response to end the chat."
        )
        assert snapshot.interview_prompt_version.startswith("sha256:")
        original_system_prompt = snapshot.interview_system_prompt
        original_initial_prompt = snapshot.interview_initial_prompt
        original_prompt_version = snapshot.interview_prompt_version

        settings = session.get(UserOpenAISettings, "owner")
        settings.model = "gpt-changed-alias"
        changed_field = session.get(Field, field_id)
        changed_field.custom_system_message = "Changed system prompt"
        changed_field.custom_initial_message = "Changed opening prompt"
        session.add_all([settings, changed_field])
        session.commit()

    second_state = asyncio.run(load_chat())

    with Session(chat_engine) as session:
        unchanged = session.exec(
            select(FieldValue).where(FieldValue.id == field_value_id)
        ).one()
        assert unchanged.interview_model == "gpt-test-alias"
        assert unchanged.interview_system_prompt == original_system_prompt
        assert unchanged.interview_initial_prompt == original_initial_prompt
        assert unchanged.interview_prompt_version == original_prompt_version

    assert first_state.configured_model == "gpt-test-alias"
    assert second_state.configured_model == "gpt-test-alias"
    assert second_state.api_reported_model_versions == "gpt-test-2026-08-12"
    assert second_state.system_message == original_system_prompt
    assert second_state.initial_message == original_initial_prompt


def test_historical_chat_is_not_backfilled_with_current_settings(chat_engine):
    with Session(chat_engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()
        session.add(
            UserOpenAISettings(
                user_id=user.user_id,
                api_key="secret-test-key",
                model="current-model-must-not-be-used",
            )
        )
        field = Field(
            form_id=form.id,
            name="question",
            type_=FieldType.text,
            debriefing=True,
            prompt="Current prompt must not be used",
            min_debriefing_time=0,
            max_debriefing_time=0,
            ordering=1.0,
        )
        response = Response(client_token="respondent", form_id=form.id)
        session.add_all([field, response])
        session.flush()
        field_value = FieldValue(
            field_id=field.id,
            response_id=response.id,
            value="Legacy answer",
            debriefing='[{"role": "assistant", "content": "Legacy chat"}]',
        )
        session.add(field_value)
        session.flush()
        form_id = form.id
        field_id = field.id
        field_value_id = field_value.id
        session.commit()

    async def load_chat():
        with Session(chat_engine) as session:
            loaded_form = session.get(Form, form_id)
            loaded_field = session.get(Field, field_id)

        root = rx.State(_reflex_internal_init=True)
        entry_state = await root.get_state(FormEntryState)
        tab_state = await root.get_state(FormEntryTabState)
        chat_state = await root.get_state(ChatState)
        entry_state.client_token = "respondent"
        entry_state.form = loaded_form
        entry_state.pending_debriefing_field_id = field_id
        tab_state.active_tab = 0
        tab_state.fields = [[loaded_field]]
        await ChatState.on_load.fn(chat_state)
        return chat_state

    state = asyncio.run(load_chat())

    with Session(chat_engine) as session:
        historical = session.get(FieldValue, field_value_id)
        assert historical.interview_model == ""
        assert historical.interview_prompt_version == ""
        assert historical.interview_system_prompt == ""
        assert historical.interview_initial_prompt == ""

    assert state.done
    assert "predates model and prompt tracking" in state.error
