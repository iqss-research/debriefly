import reflex as rx

from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.template import template


@rx.page(route="/admin", title="Admin", on_load=MainState.init_admin)
@template
def admin() -> rx.Component:
    return rx.vstack(
        rx.heading("Administration", size="6"),
        rx.text(
            "Local authentication is active. Global configuration changes are "
            "authorized by the server-side admin role."
        ),
        rx.link("Open global configuration", href="/config"),
        align="start",
        spacing="4",
    )
