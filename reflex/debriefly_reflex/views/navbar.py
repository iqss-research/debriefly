import reflex as rx
import reflex_clerk as clerk


def clerk_navbar() -> rx.Component:
    return rx.hstack(
        clerk.signed_out(
            clerk.sign_in_button(rx.button("Sign In")),
            clerk.sign_up_button(rx.button("Sign Up")),
        ),
        clerk.signed_in(
            rx.box(rx.text(clerk.ClerkState.user.first_name)),
            rx.cond(
                clerk.ClerkState.user.has_image,
                rx.chakra.avatar(
                    src=clerk.ClerkState.user.image_url,
                    name=clerk.ClerkState.user.first_name,
                    size="sm",
                ),
            ),
            clerk.sign_out_button(rx.button("Sign Out")),
        ),
    )


def navbar():
    return rx.flex(
        rx.badge(
            rx.icon(tag="mails", size=28),
            rx.heading("Debriefly", size="6"),
            radius="large",
            align="center",
            color_scheme="blue",
            variant="surface",
            padding="0.65rem",
        ),
        rx.spacer(),
        rx.hstack(
            clerk_navbar(),
            rx.color_mode.button(),
            align="center",
            spacing="3",
        ),
        spacing="2",
        flex_direction=["column", "column", "row"],
        align="center",
        width="100%",
        top="0px",
    )
