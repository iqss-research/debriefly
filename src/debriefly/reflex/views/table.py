import reflex as rx
from ..backend.backend import State, Question
from ..components.form_field import form_field


def _header_cell(text: str, icon: str):
    return rx.table.column_header_cell(
        rx.hstack(
            rx.icon(icon, size=18),
            rx.text(text),
            align="center",
            spacing="2",
        ),
    )


def _add_question_button() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(
                rx.icon("plus", size=26),
                rx.text("Add Question", size="4", display=["none", "none", "block"]),
                size="3",
            ),
        ),
        rx.dialog.content(
            rx.hstack(
                rx.badge(
                    rx.icon(tag="message-circle-question", size=34),
                    color_scheme="blue",
                    radius="full",
                    padding="0.65rem",
                ),
                rx.vstack(
                    rx.dialog.title(
                        "Question",
                        weight="bold",
                        margin="0",
                    ),
                    rx.dialog.description(
                        "Fill the form with the question's info",
                    ),
                    spacing="1",
                    height="100%",
                    align_items="start",
                ),
                height="100%",
                spacing="4",
                margin_bottom="1.5em",
                align_items="center",
                width="100%",
            ),
            rx.flex(
                rx.form.root(
                    rx.flex(
                        rx.vstack(
                            form_field(
                                "Question Text",
                                "Ask a question",
                                "text",
                                "question_text",
                                "message-circle-question",
                            ),
                            width="100%",
                        ),
                        width="100%",
                        direction="column",
                        spacing="3",
                    ),
                    rx.flex(
                        rx.dialog.close(
                            rx.button(
                                "Cancel",
                                variant="soft",
                                color_scheme="gray",
                            ),
                        ),
                        rx.form.submit(
                            rx.dialog.close(
                                rx.button("Submit Question"),
                            ),
                            as_child=True,
                        ),
                        padding_top="2em",
                        spacing="3",
                        mt="4",
                        justify="end",
                    ),
                    on_submit=State.add_question_to_db,
                    reset_on_submit=False,
                ),
                width="100%",
                direction="column",
                spacing="4",
            ),
            width="100%",
            max_width="450px",
            justify=["end", "end", "start"],
            padding="1.5em",
            border=f"2.5px solid {rx.color('accent', 7)}",
            border_radius="25px",
        ),
    )


def _show_question(question: Question):
    return rx.table.row(
        rx.table.cell(question.id),
        rx.table.cell(question.question_text),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    rx.icon("bot", size=22),
                    rx.text("Analyze", size="3"),
                    color_scheme="blue",
                    on_click=State.analyze(question),
                    disabled=State.gen_response,
                ),
                rx.alert_dialog.root(
                    rx.alert_dialog.trigger(
                        rx.icon_button(
                            rx.icon("file-plus-2", size=22),
                            size="2",
                            color_scheme="green",
                        ),
                    ),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("Generate Survey"),
                        rx.alert_dialog.description(
                            "This will create a new Qualtrics survey with this question. Are you sure?",
                        ),
                        rx.flex(
                            rx.alert_dialog.cancel(
                                rx.button("Cancel"),
                            ),
                            rx.alert_dialog.action(
                                rx.button("Create"),
                                on_click=State.create_qualtrics_survey(question),
                            ),
                            spacing="3",
                        ),
                    ),
                ),
                _update_question_dialog(question),
                rx.icon_button(
                    rx.icon("trash-2", size=22),
                    on_click=lambda: State.delete_question(getattr(question, "id")),
                    size="2",
                    variant="solid",
                    color_scheme="red",
                ),
                min_width="max-content",
            )
        ),
        style={"_hover": {"bg": rx.color("accent", 2)}},
        align="center",
    )


def _update_question_dialog(question):
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.icon_button(
                rx.icon("square-pen", size=22),
                color_scheme="green",
                size="2",
                variant="solid",
                on_click=lambda: State.get_question(question),
            ),
        ),
        rx.dialog.content(
            rx.hstack(
                rx.badge(
                    rx.icon(tag="square-pen", size=34),
                    color_scheme="blue",
                    radius="full",
                    padding="0.65rem",
                ),
                rx.vstack(
                    rx.dialog.title(
                        "Edit Question",
                        weight="bold",
                        margin="0",
                    ),
                    rx.dialog.description(
                        "Edit the question's info",
                    ),
                    spacing="1",
                    height="100%",
                    align_items="start",
                ),
                height="100%",
                spacing="4",
                margin_bottom="1.5em",
                align_items="center",
                width="100%",
            ),
            rx.flex(
                rx.form.root(
                    rx.flex(
                        rx.vstack(
                            form_field(
                                "Question Text",
                                "Ask a question",
                                "text",
                                "question_text",
                                "message-circle-question",
                                question.question_text,
                            ),
                            width="100%",
                        ),
                        width="100%",
                        direction="column",
                        spacing="3",
                    ),
                    rx.flex(
                        rx.dialog.close(
                            rx.button(
                                "Cancel",
                                variant="soft",
                                color_scheme="gray",
                            ),
                        ),
                        rx.form.submit(
                            rx.dialog.close(
                                rx.button("Update Question"),
                            ),
                            as_child=True,
                        ),
                        padding_top="2em",
                        spacing="3",
                        mt="4",
                        justify="end",
                    ),
                    on_submit=State.update_question_to_db,
                    reset_on_submit=False,
                ),
                width="100%",
                direction="column",
                spacing="4",
            ),
            max_width="450px",
            padding="1.5em",
            border=f"2px solid {rx.color('accent', 7)}",
            border_radius="25px",
        ),
    )


def main_table():
    return rx.fragment(
        rx.vstack(
            rx.hstack(
                _add_question_button(),
                rx.spacer(),
                rx.cond(
                    State.sort_reverse,
                    rx.icon(
                        "arrow-down-z-a",
                        size=28,
                        stroke_width=1.5,
                        cursor="pointer",
                        on_click=State.toggle_sort,
                    ),
                    rx.icon(
                        "arrow-down-a-z",
                        size=28,
                        stroke_width=1.5,
                        cursor="pointer",
                        on_click=State.toggle_sort,
                    ),
                ),
                rx.select(
                    ["id", "question_text"],
                    placeholder="Sort By: ID",
                    size="3",
                    on_change=lambda sort_value: State.sort_values(sort_value),
                ),
                rx.input(
                    rx.input.slot(rx.icon("search")),
                    placeholder="Search here...",
                    size="3",
                    max_width="225px",
                    width="100%",
                    variant="surface",
                    on_change=lambda value: State.filter_values(value),
                ),
            ),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        _header_cell("ID", "square-user-round"),
                        _header_cell("Question", "mail"),
                        _header_cell("Actions", "cog"),
                    ),
                ),
                rx.table.body(rx.foreach(State.questions, _show_question)),
                variant="surface",
                size="3",
                width="100%",
            ),
            justify="end",
            align="center",
            spacing="3",
            wrap="wrap",
            width="100%",
            padding_bottom="1em",
        ),
    )
