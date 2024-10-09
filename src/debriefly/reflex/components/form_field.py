import reflex as rx
from typing import List


def form_field(
    label: str,
    placeholder: str,
    type: str,
    name: str,
    icon: str,
    default_value: str = "",
) -> rx.Component:
    return rx.form.field(
        rx.flex(
            rx.hstack(
                rx.icon(icon, size=16, stroke_width=1.5),
                rx.form.label(label),
                align="center",
                spacing="2",
            ),
            rx.form.control(
                rx.input(
                    placeholder=placeholder, type=type, default_value=default_value
                ),
                as_child=True,
            ),
            direction="column",
            spacing="1",
        ),
        name=name,
        width="100%",
    )


def form_field_radio(
    name: str,
    values: List[str],
    default_value: str = "TEXT",
) -> rx.Component:
    return rx.vstack(
        rx.radio(
            values,
            name=name,
            direction="row",
            as_child=True,
            required=True,
            default_value=default_value,
        )
    )


def form_field_boxes(
    label: str, name: str, values: List[str], icon: str = "message-circle-question"
) -> rx.Component:
    return rx.form.field(
        rx.flex(
            rx.hstack(
                rx.icon(icon, size=16, stroke_width=1.5),
                rx.form.label(label),
                align="center",
                spacing="2",
            ),
            rx.foreach(
                values,
                lambda value, index: rx.form.control(
                    rx.input(default_value="", name=f"{name}[{index}]"), as_child=True
                ),
            ),
            direction="column",
            spacing="1",
        ),
        name=name,
        width="100%",
    )
