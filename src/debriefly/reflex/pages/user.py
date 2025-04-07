from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState
import reflex as rx


@rx.page(route="/user", title="User", on_load=[MainState.init])
@template
def user() -> rx.Component:
    return rx.vstack(
        rx.flex(
            rx.vstack(
                rx.hstack(
                    rx.icon("square-user-round"),
                    rx.heading("Qualtrics Integration", size="5"),
                    align="center",
                ),
                rx.text("Update your Qualtrics Information.", size="3"),
                width="100%",
            ),
            rx.form.root(
                rx.vstack(
                    rx.button("Update", type="submit", width="100%"),
                    width="100%",
                    spacing="5",
                ),
                on_submit=MainState.update_user,
                reset_on_submit=True,
                width="100%",
                max_width="325px",
            ),
            width="100%",
            spacing="4",
            flex_direction=["column", "column", "row"],
        ),
        spacing="6",
        width="100%",
        max_width="800px",
    )
