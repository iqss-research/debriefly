from ..templates import template
from ..components.profile_input import profile_input
from ..backend.backend import State
import reflex as rx
import reflex_clerk as clerk


@template(route="/profile", title="Profile")
def profile() -> rx.Component:
    return rx.vstack(
        clerk.protect(
            rx.vstack(
                rx.hstack(
                    rx.icon("shield-check"),
                    rx.heading("Access Level", size="5"),
                    align="center",
                ),
                rx.text("You have admin access to debriefly.", size="3"),
                width="100%",
            ),
            role="org:admin",
        ),
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
                    profile_input(
                        "Qualtrics API Token",
                        "qualtrics_api_token",
                        "",
                        "text",
                        "braces",
                        State.profile.qualtrics_api_token,
                    ),
                    profile_input(
                        "Qualtrics Client ID",
                        "qualtrics_client_id",
                        "",
                        "text",
                        "user",
                        State.profile.qualtrics_client_id,
                    ),
                    profile_input(
                        "Qualtrics Client Secret",
                        "qualtrics_client_secret",
                        "",
                        "text",
                        "key-round",
                        State.profile.qualtrics_client_secret,
                    ),
                    profile_input(
                        "Qualtrics Data Center",
                        "qualtrics_data_center",
                        "",
                        "text",
                        "server",
                        State.profile.qualtrics_data_center,
                    ),
                    rx.button("Update", type="submit", width="100%"),
                    width="100%",
                    spacing="5",
                ),
                on_submit=State.update_profile,
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
