import reflex as rx
import reflex_clerk as clerk
from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState


@rx.page(
    route="/admin",
    title="Admin View",
    on_load=MainState.init,
)
@template
def admin() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Switch to Admin View", size="4", weight="bold", mb="1em"),
            clerk.organization_switcher(),
        ),
    )
