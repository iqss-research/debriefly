import reflex as rx
import reflex_clerk as clerk
from debriefly.reflex import styles
from debriefly.reflex.backend.backend import MainState

clerk.ClerkState.set_fetch_user_on_auth(False)

try:
    import debriefly.reflex.pages  # noqa
except ValueError as e:
    """ "
    ClerkProvider doesn't work at import time if the appropriate envvars
    are not set to their correct value. Since this interferes with basic
    reflex operations like 'reflex db init', 'reflex db migrate' etc.,
    we ignore any such errors during import of this module.
    Of couse, the individual pages will still be protected as long as they
    have the appropriate @template decorator.
    """
    if str(e).startswith("Clerk"):
        pass
    else:
        raise

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
