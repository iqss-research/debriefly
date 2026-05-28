import reflex as rx
from debriefly.reflex.backend.models import BundleItem, Field, FieldType, Option
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
    def render_option(option: Option) -> rx.Component:
        return component(
            option.label,
            value=option_value_label_id(option),
        )

    typed_options = rx.Var.create_safe(options, _var_is_string=False).to(list[Option])
    return rx.foreach(typed_options, render_option)


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
    def render_option(option: Option) -> rx.Component:
        return checkbox_item(field, option)

    return rx.cond(
        field.options,
        rx.foreach(
            rx.Var.create_safe(field.options, _var_is_string=False).to(list[Option]),
            render_option,
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
            min=field.scale_min,
            max=field.scale_max,
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


def bundle_field_input_name(field: Field, item: BundleItem) -> str:
    return f"{field.name}___{item.id}"


def bundle_option_input_name(field: Field, item: BundleItem, option: Option) -> str:
    return f"{field.name}___{item.id}___{option.id}"


def bundle_radio_item(field: Field, item: BundleItem, option: Option) -> rx.Component:
    return radio_item(option.label, value=option_value_label_id(option))


def bundle_checkbox_item(
    field: Field, item: BundleItem, option: Option
) -> rx.Component:
    return rx.box(
        rx.checkbox(
            option.label,
            value=option_value_label_id(option),
            name=bundle_option_input_name(field, item, option),
        ),
        margin_right="2em",
    )


def bundle_radio(field: Field, item: BundleItem, editing: bool = False) -> rx.Component:
    def render_option(option: Option) -> rx.Component:
        return bundle_radio_item(field, item, option)

    return rx.cond(
        field.options,
        rx.radio.root(
            rx.vstack(
                rx.foreach(
                    rx.Var.create_safe(field.options, _var_is_string=False).to(
                        list[Option]
                    ),
                    render_option,
                ),
                align="start",
            ),
            name=bundle_field_input_name(field, item),
            required=rx.cond(editing, False, field.required),
        ),
        rx.text("No options defined"),
    )


def bundle_checkbox(field: Field, item: BundleItem) -> rx.Component:
    def render_option(option: Option) -> rx.Component:
        return bundle_checkbox_item(field, item, option)

    return rx.cond(
        field.options,
        rx.foreach(
            rx.Var.create_safe(field.options, _var_is_string=False).to(list[Option]),
            render_option,
        ),
        rx.text("No options defined"),
    )


def bundle_scale(field: Field, item: BundleItem) -> rx.Component:
    return rx.vstack(
        rx.slider(
            name=bundle_field_input_name(field, item),
            default_value=field.scale_min,
            min=field.scale_min,
            max=field.scale_max,
            step=1,
            width="100%",
        ),
        rx.hstack(
            rx.text(field.scale_min, size="1"),
            rx.spacer(),
            rx.text(field.scale_max, size="1"),
            width="100%",
        ),
        spacing="2",
        width="100%",
    )


def bundle_item_input(
    field: Field, item: BundleItem, editing: bool = False
) -> rx.Component:
    name = bundle_field_input_name(field, item)
    return rx.match(
        field.type_,
        (FieldType.checkbox.value, bundle_checkbox(field, item)),
        (FieldType.radio.value, bundle_radio(field, item, editing=editing)),
        (
            FieldType.textarea.value,
            rx.text_area(
                placeholder=field.prompt,
                name=name,
                required=rx.cond(editing, False, field.required),
            ),
        ),
        (FieldType.scale.value, bundle_scale(field, item)),
        rx.input(
            placeholder=field.prompt,
            type=field.type_.to(str),
            name=name,
            aria_label=name,
            required=rx.cond(editing, False, field.required),
        ),
    )


def bundle_item_view(
    field: Field, item: BundleItem, editing: bool = False
) -> rx.Component:
    return rx.vstack(
        rx.text(item.label, weight="medium"),
        bundle_item_input(field, item, editing=editing),
        spacing="2",
        width="100%",
        align="start",
    )


def field_bundle(field: Field, editing: bool = False) -> rx.Component:
    def render_item(item: BundleItem) -> rx.Component:
        return bundle_item_view(field, item, editing=editing)

    return rx.cond(
        field.bundle_items,
        rx.vstack(
            rx.foreach(
                rx.Var.create_safe(field.bundle_items, _var_is_string=False).to(
                    list[BundleItem]
                ),
                render_item,
            ),
            spacing="4",
            width="100%",
        ),
        rx.text("No bundled items defined"),
    )


def field_single_input(field: Field, editing: bool = False):
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


def field_input(field: Field, editing: bool = False):
    return rx.cond(
        field.bundled,
        field_bundle(field, editing=editing),
        field_single_input(field, editing=editing),
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
