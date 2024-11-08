import reflex as rx
from debriefly.reflex.components.analyze.loading_icon import loading_icon
from debriefly.reflex.components.analyze.state import QA, AnalysisState
from debriefly.reflex.form_designer import style, routes
from debriefly.reflex.form_designer.pages import ResponsesState

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
        rx.box(rx.foreach(AnalysisState.chat, message), width="100%"),
        py="8",
        flex="1",
        width="100%",
        padding_x="4px",
        align_self="center",
        overflow="hidden",
        padding_bottom="5em",
    )


def insert_chat_button(txts: list[str]) -> rx.Component:
    return rx.hstack(
        rx.foreach(
            txts,
            lambda txt: rx.button(
                txt,
                size="1",
                variant="soft",
                color_scheme="gray",
                radius="full",
                on_click=AnalysisState.process_question({"question": txt}),
            ),
        )
    )


def action_bar() -> rx.Component:
    return rx.center(
        rx.vstack(
            insert_chat_button(
                [
                    "Enumerate the topic of the responses!",
                    "Give me the summary of the data",
                ]
            ),
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
                            placeholder="Type something..",
                            id="question",
                            width=["15em", "20em", "45em", "50em", "50em", "50em"],
                        ),
                        rx.cond(
                            ~AnalysisState.done,
                            rx.button(
                                rx.cond(
                                    AnalysisState.processing,
                                    loading_icon(height="1em"),
                                    rx.text("Send"),
                                ),
                                type="submit",
                            ),
                        ),
                        align_items="center",
                    ),
                    is_disabled=AnalysisState.processing,
                ),
                on_submit=AnalysisState.process_question,
                reset_on_submit=True,
            ),
            align_items="center",
        ),
        width="100%",
    )


def chat_ui() -> rx.Component:
    return style.layout(
        rx.link("< Responses", href=routes.form_responses(ResponsesState.form.id)),
        rx.vstack(rx.heading(AnalysisState.form.name), chat(), action_bar()),
    )
