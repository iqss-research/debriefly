import reflex as rx
from debriefly.reflex.backend.models import Field, FieldType, Option
from typing import Any


class OptionItemCallable:
    def __call__(
        self, *children: rx.Component, value: rx.Var[str], **props
    ) -> rx.Component:
        ...


def option_value_label_id(option: Option) -> rx.Component:
    return rx.cond(
        option.value != "",
        option.value,
        rx.cond(
            option.label != "",
            option.label,
            option.id.to_string(),
        ),
    )


def foreach_field_options(
    options: list[Option], component: OptionItemCallable
) -> rx.Component:
    return rx.foreach(
        options,
        lambda option: component(
            option.label,
            value=option_value_label_id(option),
        ),
    )


def radio_item(*children: rx.Component, value: rx.Var[str], **props) -> rx.Component:
    return rx.hstack(
        rx.radio.item(value=value, **props),
        *children,
    )


def field_radio(field: Field, editing: bool = False) -> rx.Component:
    return rx.cond(
        field.options,
        rx.radio.root(
            rx.vstack(
                foreach_field_options(field.options, radio_item),
                align="start",
            ),
            name=field.name,
            required=rx.cond(editing, False, field.required),
        ),
        rx.text("No options defined"),
    )


def checkbox_item(field: Field, option: Option):
    value = option_value_label_id(option)
    return rx.box(
        rx.checkbox(
            option.label,
            value=value,
            name=f"{field.name}___{value}",
        ),
        margin_right="2em",
    )


def field_checkbox(field: Field) -> rx.Component:
    return rx.cond(
        field.options,
        rx.foreach(
            field.options,
            lambda option: checkbox_item(field, option),
        ),
        rx.text("No options defined"),
    )


class ScaleValueState(rx.State):
    """Stores the most-recent numeric value of every scale slider."""

    values: dict[str, int] = {}

    def set_value(self, name: str, v: Any):
        """`v` from rx.slider is usually a one-element list like ['38']."""
        if isinstance(v, (list, tuple)):
            if not v:
                return
            v = v[0]

        if v is None:
            return

        try:
            v_int = int(float(v))
        except (ValueError, TypeError):
            return

        self.values = {**self.values, name: v_int}


def field_scale(field: Field) -> rx.Component:
    """Slider that shows its current numeric value in real time."""
    return rx.vstack(
        rx.text(
            "Current Value: ",
            rx.cond(
                ScaleValueState.values.contains(field.name),
                ScaleValueState.values[field.name].to_string(),
                field.scale_min.to_string(),
            ),
        ),
        rx.slider(
            name=field.name,
            default_value=field.scale_min,
            min_=field.scale_min,
            max_=field.scale_max,
            step=1,
            width="100%",
            on_change=lambda v: ScaleValueState.set_value(field.name, v),
        ),
        rx.hstack(
            rx.text(field.scale_min),  # left anchor
            rx.spacer(),
            rx.spacer(),
            rx.text(field.scale_max),  # right anchor
        ),
        width="100%",
    )


def field_input(field: Field, editing: bool = False):
    return rx.match(
        field.type_,
        (FieldType.checkbox.value, field_checkbox(field)),
        (FieldType.radio.value, field_radio(field, editing=editing)),
        (
            FieldType.textarea.value,
            rx.text_area(
                placeholder=field.prompt,
                name=field.name,
            ),
        ),
        (FieldType.scale.value, field_scale(field)),
        (FieldType.static.value, rx.spacer()),
        (FieldType.pagebreak.value, rx.divider()),
        rx.input(
            placeholder=field.prompt,
            type=field.type_.to(str),
            name=field.name,
            aria_label=field.name,
            required=field.required,
        ),
    )


def field_prompt(field: Field, markdown: str = "", show_name: bool = False):
    name = f" ({field.name})" if show_name else ""
    return rx.match(
        field.type_,
        (
            FieldType.static.value,
            rx.markdown(rx.cond(markdown == "", field.prompt, markdown)),
        ),
        (FieldType.pagebreak.value, rx.text("------ Page Break ------")),
        rx.cond(
            field.prompt != "",
            rx.text(f"{field.prompt}{name}"),
            rx.cond(
                field.name != "",
                rx.text(field.name),
                rx.text("[unnamed field]"),
            ),
        ),
    )


def field_view(field: Field, markdown: str = ""):
    return rx.card(
        rx.hstack(
            # https://github.com/reflex-dev/reflex/issues/1655
            rx.box(field_prompt(field, markdown)),
            rx.text(rx.cond(field.required, "*", "")),
        ),
        rx.hstack(
            field_input(field),
            flex_wrap="wrap",
        ),
    )
