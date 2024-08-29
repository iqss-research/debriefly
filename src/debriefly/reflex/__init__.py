import reflex as rx
from . import styles
from .backend.backend import State
from .pages import *  # noqa


app = rx.App(
    style=styles.base_style,
    stylesheets=styles.base_stylesheets,
    title="Dashboard Template",
    description="A dashboard template for Reflex.",
    onloady=State.load_entries,
)
