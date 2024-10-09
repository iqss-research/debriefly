import reflex as rx
from debriefly.reflex import styles
import debriefly.reflex.pages  # noqa
from debriefly.reflex.backend.backend import MainState


# Add these dynamic route vars early, so they can be referenced in the titles.
if "form_id" not in rx.State.__fields__:
    rx.State.add_var("form_id", str, "")
if "field_id" not in rx.State.__fields__:
    rx.State.add_var("field_id", str, "")


app = rx.App(
    style=styles.base_style,
    stylesheets=styles.base_stylesheets,
    title="Debriefly",
    description="Debriefing App for Qualtrics",
    onload=MainState.init,
)
