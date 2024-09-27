import reflex as rx
from debriefly.reflex.backend.backend import AnswerState as State
from debriefly.reflex.backend.models import Answer


def _header_cell(text: str, icon: str):
    return rx.table.column_header_cell(
        rx.hstack(
            rx.icon(icon, size=18),
            rx.text(text),
            align="center",
            spacing="2",
        ),
    )


def _show_answer(answer: Answer):
    return rx.table.row(
        rx.table.cell(answer.id),
        rx.table.cell(answer.answer[:30]),
        rx.table.cell(rx.moment(answer.created_on, format="MM/DD/YY HH:mm")),
        rx.table.cell(
            rx.hstack(
                rx.link(
                    rx.icon_button(
                        rx.icon("zoom-in", size=22),
                        size="2",
                        color_scheme="blue",
                    ),
                    href=f"/answer/{answer.id}",
                ),
                rx.alert_dialog.root(
                    rx.tooltip(
                        rx.alert_dialog.trigger(
                            rx.icon_button(
                                rx.icon("trash-2", size=22),
                                size="2",
                                color_scheme="red",
                            )
                        ),
                        content="Delete answer",
                    ),
                    rx.alert_dialog.content(
                        rx.alert_dialog.title("Delete answer"),
                        rx.alert_dialog.description(
                            "Are you sure?",
                        ),
                        rx.flex(
                            rx.alert_dialog.cancel(
                                rx.button("Cancel"),
                            ),
                            rx.alert_dialog.action(
                                rx.button("Delete"),
                                on_click=lambda: State.delete_answer(
                                    getattr(answer, "id")
                                ),
                            ),
                            spacing="3",
                        ),
                    ),
                ),
                min_width="max-content",
            )
        ),
        style={"_hover": {"bg": rx.color("accent", 2)}},
        align="center",
    )


def main_table():
    return rx.fragment(
        rx.vstack(
            rx.hstack(
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
                    ["id"],
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
                        _header_cell("Answer", "mail"),
                        _header_cell("Submitted", "clock"),
                        _header_cell("Actions", "cog"),
                    ),
                ),
                rx.table.body(rx.foreach(State.answers, _show_answer)),
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
