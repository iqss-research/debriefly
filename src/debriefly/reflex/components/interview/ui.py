import reflex as rx
from reflex_chakra import form as chakra_form, form_control as chakra_form_control

from debriefly.reflex.components.interview.state import (
    HumanInterviewSession,
    InterviewMessage,
    InterviewerListState,
    InterviewerState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_BG = rx.color("mauve", 4)
_USER_FG = rx.color("mauve", 12)
_INTERVIEWER_BG = rx.color("accent", 4)
_INTERVIEWER_FG = rx.color("accent", 12)
_MSG_STYLE = dict(
    display="inline-block",
    padding="1em",
    border_radius="8px",
    max_width=["30em", "30em", "50em", "50em", "50em", "50em"],
)


def _interview_message(msg: InterviewMessage) -> rx.Component:
    return rx.box(
        rx.cond(
            msg.role == "user",
            # Respondent message — right-aligned
            rx.box(
                rx.markdown(
                    msg.content,
                    background_color=_USER_BG,
                    color=_USER_FG,
                    **_MSG_STYLE,
                ),
                text_align="right",
                margin_top="1em",
            ),
            # Interviewer message — left-aligned
            rx.box(
                rx.markdown(
                    msg.content,
                    background_color=_INTERVIEWER_BG,
                    color=_INTERVIEWER_FG,
                    **_MSG_STYLE,
                ),
                text_align="left",
                padding_top="1em",
            ),
        ),
        width="100%",
    )


# ---------------------------------------------------------------------------
# Session detail (interviewer view)
# ---------------------------------------------------------------------------


def interviewer_ui() -> rx.Component:
    return rx.cond(
        ~InterviewerState.loaded,
        rx.center(rx.spinner(), min_height="100vh"),
        rx.cond(
            InterviewerState.error != "",
            rx.center(
                rx.card(
                    rx.text(InterviewerState.error),
                    max_width="32rem",
                    text_align="center",
                    p="6",
                ),
                min_height="100vh",
            ),
            rx.vstack(
                # Context banner
                rx.card(
                    rx.vstack(
                        rx.text("Interview session", weight="bold", size="2"),
                        rx.text(
                            "Question: ",
                            rx.text.span(InterviewerState.field_prompt, weight="bold"),
                        ),
                        rx.text(
                            "Respondent's answer: ",
                            rx.text.span(
                                InterviewerState.respondent_answer, weight="bold"
                            ),
                        ),
                        spacing="1",
                    ),
                    width="100%",
                    background_color=rx.color("gray", 2),
                    p="3",
                ),
                # Transcript
                rx.box(
                    rx.foreach(InterviewerState.messages, _interview_message),
                    width="100%",
                    flex="1",
                    overflow_y="auto",
                    padding_bottom="6em",
                ),
                # Input area
                rx.cond(
                    InterviewerState.session_done,
                    rx.center(
                        rx.badge("Interview ended", color_scheme="gray", size="2"),
                        width="100%",
                        p="4",
                    ),
                    rx.center(
                        rx.vstack(
                            chakra_form(
                                chakra_form_control(
                                    rx.hstack(
                                        rx.input(
                                            placeholder="Type your reply here",
                                            id="reply",
                                            width=[
                                                "15em",
                                                "20em",
                                                "45em",
                                                "50em",
                                                "50em",
                                                "50em",
                                            ],
                                        ),
                                        rx.button("Send", type="submit"),
                                        rx.button(
                                            "End Interview",
                                            color_scheme="tomato",
                                            type="button",
                                            on_click=InterviewerState.end_interview,
                                        ),
                                        align_items="center",
                                        spacing="2",
                                    ),
                                ),
                                on_submit=InterviewerState.send_reply,
                                reset_on_submit=True,
                            ),
                            align_items="center",
                            width="100%",
                        ),
                        position="sticky",
                        bottom="0",
                        left="0",
                        padding_y="16px",
                        backdrop_filter="auto",
                        backdrop_blur="lg",
                        border_top=f"1px solid {rx.color('mauve', 3)}",
                        background_color=rx.color("mauve", 2),
                        width="100%",
                    ),
                ),
                height="100vh",
                width="100%",
                spacing="0",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Session list (researcher dashboard)
# ---------------------------------------------------------------------------

_STATUS_COLOR = {"waiting": "yellow", "active": "green", "done": "gray"}


def _session_row(s: HumanInterviewSession) -> rx.Component:
    return rx.table.row(
        rx.table.cell(s.form_name),
        rx.table.cell(s.field_prompt),
        rx.table.cell(s.client_token[:12] + "…"),
        rx.table.cell(s.started_at),
        rx.table.cell(
            rx.badge(
                s.status,
                color_scheme=rx.match(
                    s.status,
                    ("waiting", "yellow"),
                    ("active", "green"),
                    ("done", "gray"),
                    "gray",
                ),
            )
        ),
        rx.table.cell(
            rx.link(
                rx.button("Open", size="1", variant="outline"),
                href="/interview/" + s.field_value_id.to(str),
            )
        ),
    )


def interviewer_list_ui() -> rx.Component:
    return rx.cond(
        ~InterviewerListState.loaded,
        rx.center(rx.spinner(), min_height="100vh"),
        rx.vstack(
            rx.heading("Human Interview Sessions", size="5", mb="4"),
            rx.cond(
                InterviewerListState.sessions.length() == 0,
                rx.text(
                    "No human interview sessions found. "
                    "Enable 'Human Interviewer Mode' on a debriefing question to start.",
                    color=rx.color("gray", 11),
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Form"),
                            rx.table.column_header_cell("Question"),
                            rx.table.column_header_cell("Respondent"),
                            rx.table.column_header_cell("Started"),
                            rx.table.column_header_cell("Status"),
                            rx.table.column_header_cell(""),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(InterviewerListState.sessions, _session_row)
                    ),
                    width="100%",
                ),
            ),
            width="100%",
            max_width="72rem",
            margin="0 auto",
            padding="2em",
        ),
    )
