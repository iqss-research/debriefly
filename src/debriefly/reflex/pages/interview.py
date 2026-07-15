import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.components.interview.state import (
    InterviewerListState,
    InterviewerState,
)
from debriefly.reflex.components.interview.ui import interviewer_ui, interviewer_list_ui


@rx.page(
    route="/interview",
    title="Human Interview Sessions",
    on_load=[MainState.init, InterviewerListState.on_load],
)
@template
def interview_list() -> rx.Component:
    return interviewer_list_ui()


@rx.page(
    route="/interview/[interview_session_id]",
    title="Human Interview",
    on_load=[MainState.init, InterviewerState.on_load],
)
@template
def interview_session() -> rx.Component:
    return interviewer_ui()
