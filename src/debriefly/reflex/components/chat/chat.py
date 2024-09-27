import reflex as rx
from debriefly.reflex.components.chat.loading_icon import loading_icon
from debriefly.reflex.components.chat.state import QA, State


message_style = dict(
    display="inline-block",
    padding="1em",
    border_radius="8px",
    max_width=["30em", "30em", "50em", "50em", "50em", "50em"],
)


def message(qa: QA) -> rx.Component:
    return rx.box(
        rx.cond(
            qa.question != "",
            rx.box(
                rx.markdown(
                    qa.question,
                    background_color=rx.color("mauve", 4),
                    color=rx.color("mauve", 12),
                    **message_style,
                ),
                text_align="right",
                margin_top="1em",
            ),
        ),
        rx.box(
            rx.markdown(
                qa.answer,
                background_color=rx.color("accent", 4),
                color=rx.color("accent", 12),
                **message_style,
            ),
            text_align="left",
            padding_top="1em",
        ),
        width="100%",
    )


def chat() -> rx.Component:
    return rx.vstack(
        rx.box(rx.foreach(State.chat, message), width="100%"),
        py="8",
        flex="1",
        width="100%",
        padding_x="4px",
        align_self="center",
        overflow="hidden",
        padding_bottom="5em",
    )


def action_bar() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.chakra.form(
                rx.chakra.form_control(
                    rx.hstack(
                        rx.input(
                            rx.input.slot(
                                rx.tooltip(
                                    rx.icon("info", size=18),
                                    content="Enter a question to get a response.",
                                )
                            ),
                            placeholder="Type something...",
                            id="question",
                            width=["15em", "20em", "45em", "50em", "50em", "50em"],
                        ),
                        rx.cond(
                            ~State.done,
                            rx.button(
                                rx.cond(
                                    State.processing,
                                    loading_icon(height="1em"),
                                    rx.text("Send"),
                                ),
                                type="submit",
                            ),
                        ),
                        align_items="center",
                    ),
                    is_disabled=State.processing,
                ),
                on_submit=State.process_question,
                reset_on_submit=True,
            ),
            align_items="center",
        ),
        position="sticky",
        bottom="0",
        left="0",
        padding_y="16px",
        backdrop_filter="auto",
        backdrop_blur="lg",
        border_top=f"1px solid {rx.color('mauve', 3)}",
        background_color=rx.color("mauve", 2),
        align_items="stretch",
        width="100%",
    )


def title_bar() -> rx.Component:
    return rx.flex(
        rx.text(
            f"Debriefing (answer {State.answer_id})",
            size="4xl",
        ),
        width="100%",
        padding_y="4",
        padding_x="4",
        align_items="center",
        justify_content="space-between",
        background_color=rx.color("mauve", 1),
    )


def chat_ui() -> rx.Component:
    return rx.vstack(title_bar(), chat(), action_bar())
