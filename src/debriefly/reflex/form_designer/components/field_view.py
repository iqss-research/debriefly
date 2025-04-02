import reflex as rx
from debriefly.reflex.backend.models import Field, FieldType, Option


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
