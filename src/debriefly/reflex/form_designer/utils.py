"""Miscellaneous utility functions."""

import reflex as rx


def quoted_var(value: str) -> rx.Var:
    """Allows a bare string to be used in a page title with other Vars."""
    return rx.Var.create_safe(f"'{value}'", _var_is_string=False, _var_is_local=True)


def focus_input_in_class(class_name: str) -> rx.event.EventSpec:
    """Focus the last input in the last class.

    Args:
        class_name: The class name to search for.

    Returns:
        A reflex component.
    """
    # Use window.setTimeout to allow react enough time to add new input elements.
    return rx.call_script(
        "window.setTimeout("
        f"() => Array.from(document.querySelectorAll('.{class_name} input')).pop().focus(),"
        "100)"
    )
