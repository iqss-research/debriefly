import reflex as rx
import reflex_clerk as clerk
from sqlmodel import select
import json
from debriefly.reflex.backend.models import Answer
from debriefly.reflex.components.chat.chat import message_style


class State(clerk.ClerkState):
    valid: bool = False
    answer: Answer = Answer()
    messages: list[dict[str, str]] = []

    def on_load(self):
        answer_id = self.router.page.params.get("answer_id")
        with rx.session() as session:
            answer = session.exec(select(Answer).where(Answer.id == answer_id)).first()
            self.valid = answer is not None and answer.question.user_id == self.user_id
            self.answer = answer
            self.messages = json.loads(answer.debriefing)


answer_style = {
    "background_color": rx.color("mauve", 4),
    "color": rx.color("mauve", 12),
}


def main() -> rx.Component:
    return rx.cond(
        State.valid,
        rx.vstack(
            rx.heading(f"Answer ID: {State.answer.id}"),
            rx.box(
                rx.markdown(
                    State.answer.answer,
                    background_color=rx.color("teal", 4),
                    color=rx.color("mauve", 12),
                    **message_style,
                ),
                text_align="left",
                margin_top="1em",
                width="100%",
            ),
            rx.foreach(
                State.messages,
                lambda message: rx.cond(
                    message["role"] == "assistant",
                    rx.box(
                        rx.markdown(
                            message["content"],
                            background_color=rx.color("accent", 4),
                            color=rx.color("accent", 12),
                            **message_style,
                        ),
                        text_align="left",
                        padding_top="1em",
                        width="100%",
                    ),
                    rx.box(
                        rx.markdown(
                            message["content"],
                            background_color=rx.color("mauve", 4),
                            color=rx.color("mauve", 12),
                            **message_style,
                        ),
                        text_align="right",
                        margin_top="1em",
                        width="100%",
                    ),
                ),
            ),
        ),
        rx.text("Invalid Answer ID"),
    )
