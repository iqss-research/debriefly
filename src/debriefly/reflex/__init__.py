import reflex as rx

from debriefly.reflex import styles
from debriefly.reflex.auth_api import register_auth_routes
from debriefly.reflex.auth_middleware import LocalAuthMiddleware


# Import page decorators before constructing the app.
import debriefly.reflex.pages  # noqa: E402,F401


# Add dynamic route vars early, so they can be referenced in titles and state.
if "form_id" not in rx.State.__fields__:
    rx.State.add_var("form_id", str, "")
if "field_id" not in rx.State.__fields__:
    rx.State.add_var("field_id", str, "")
if "interview_session_id" not in rx.State.__fields__:
    rx.State.add_var("interview_session_id", str, "")


app = rx.App(
    style=styles.base_style,
    stylesheets=styles.base_stylesheets,
    head_components=[
        rx.el.link(rel="icon", href="/debriefly-icon.png", type="image/png"),
        rx.el.link(
            rel="apple-touch-icon",
            href="/debriefly-icon.png",
            sizes="1254x1254",
        ),
        rx.el.link(rel="shortcut icon", href="/favicon.ico", type="image/x-icon"),
    ],
    title="Debriefly",
    description="Debriefing App for Qualtrics",
)
# Run before Reflex's hydration middleware so stale researcher substates are
# cleared before any state snapshot is serialized to a newly loaded page.
app.add_middleware(LocalAuthMiddleware(), index=0)
register_auth_routes(app.api)
