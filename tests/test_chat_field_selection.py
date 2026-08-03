import asyncio

import pytest
import reflex as rx
from sqlmodel import Session, SQLModel, create_engine

import debriefly.reflex.components.chat.state as chat_state_module
from debriefly.reflex.backend.models import Form, Response, User
from debriefly.reflex.backend.models import Field, FieldType
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
