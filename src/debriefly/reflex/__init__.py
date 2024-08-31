import reflex as rx
from debriefly.reflex import styles
from debriefly.reflex.pages import *  # noqa
from debriefly.reflex.backend.backend import State


app = rx.App(
    style=styles.base_style,
    stylesheets=styles.base_stylesheets,
    title="Debriefly",
    description="Debriefing App for Qualtrics",
    onload=State.load_entries,
)
