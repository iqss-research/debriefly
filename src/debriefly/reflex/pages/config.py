from debriefly.reflex.template import template
from debriefly.reflex.components.profile_input import profile_input
from debriefly.reflex.backend.backend import MainState
import reflex as rx
import reflex_clerk as clerk


@rx.page(route="/config", title="Configuration")
@template
def config() -> rx.Component:
    return clerk.protect(
        rx.vstack(
            rx.flex(
                rx.vstack(
                    rx.hstack(
                        rx.icon("cog"),
                        rx.heading("Global Configuration", size="5"),
                        align="center",
                    ),
                    rx.text("Update App-level Configuration.", size="3"),
                    width="100%",
                ),
                rx.form.root(
                    rx.vstack(
                        rx.foreach(
                            MainState.config,
                            lambda kv: profile_input(
                                kv[0],
                                kv[0],
                                "",
                                "text",
                                "braces",
                                kv[1],
                            ),
                        ),
                        rx.button("Update", type="submit", width="100%"),
                        width="100%",
                        spacing="5",
                    ),
                    on_submit=MainState.update_profile,
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
        ),
        permission="org:app:admin",
    )
