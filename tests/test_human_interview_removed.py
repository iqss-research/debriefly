import asyncio
import importlib.util

from reflex.page import get_decorated_pages

import debriefly.reflex.pages  # noqa: F401
from debriefly.reflex.backend.models import Field, Form
from debriefly.reflex.components.chat.state import ChatState
from debriefly.reflex.components.sidebar import _sidebar_content
from debriefly.reflex.form_designer.components.field_editor import field_editor
from debriefly.reflex.form_designer.components.form_editor import (
    _enforce_automated_debriefing,
    _has_retired_human_interview,
)


def test_human_interview_pages_and_handlers_are_not_registered():
    routes = {page["route"] for page in get_decorated_pages()}

    assert not any(route.startswith("/interview") for route in routes)
    assert importlib.util.find_spec("debriefly.reflex.pages.interview") is None
    assert not hasattr(ChatState, "human_process_question")
    assert not hasattr(ChatState, "poll_human_chat")
    assert not {
        name
        for name in ChatState.event_handlers
        if "human" in name or "interview" in name
    }


def test_human_interview_controls_are_not_rendered():
    assert "Human Interviewer Mode" not in str(field_editor())
    sidebar_markup = str(_sidebar_content())
    assert "Interview Sessions" not in sidebar_markup
    assert "/interview" not in sidebar_markup


def test_forged_human_interview_flag_is_cleared():
    field = Field(interviewer_mode=True)

    normalized = _enforce_automated_debriefing(field)

    assert normalized is field
    assert normalized.interviewer_mode is False


def test_legacy_human_interview_survey_requires_explicit_conversion():
    legacy_form = Form(fields=[Field(interviewer_mode=True)])
    automated_form = Form(fields=[Field(interviewer_mode=False)])

    assert _has_retired_human_interview(legacy_form) is True
    assert _has_retired_human_interview(automated_form) is False


def test_legacy_human_interview_field_fails_closed():
    async def submit_question():
        state = ChatState(_reflex_internal_init=True)
        state.field = Field(interviewer_mode=True)
        events = []

        async for event in ChatState.process_question.fn(
            state, {"question": "private response"}
        ):
            events.append(event)

        return state, events

    state, events = asyncio.run(submit_question())

    assert events == []
    assert state.processing is False
    assert state.error == (
        "This survey uses a retired interview setting. "
        "Please contact the survey owner."
    )
