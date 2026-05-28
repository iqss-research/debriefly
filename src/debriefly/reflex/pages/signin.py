import reflex as rx
import reflex_clerk as clerk
from debriefly.reflex import styles
from debriefly.reflex.auth import (
    AUTH_FALLBACK_ROUTE,
    SIGN_IN_ROUTE,
    SIGN_IN_ROUTE_PATTERN,
)


def login_explanation() -> rx.Component:
    return rx.text(
        "Debriefly uses Clerk to manage this sign-in page and the available "
        "sign-in options. The information you submit here is used only to "
        "authenticate your account; we do not use it for any other purpose. "
        "See our ",
        rx.link(
            "Privacy Statement",
            href="/privacy",
            target="_blank",
            color=styles.accent_text_color,
            text_decoration="underline",
        ),
        ".",
        size="1",
        color=styles.text_color,
        line_height="1.5",
        text_align="center",
        width="100%",
        max_width="26rem",
    )


@rx.page(route=SIGN_IN_ROUTE_PATTERN, title="Sign In")
def signin() -> rx.Component:
    return rx.theme(
        clerk.clerk_provider(
            rx.center(
                rx.vstack(
                    clerk.sign_in(
                        routing="path",
                        path=SIGN_IN_ROUTE,
                        fallback_redirect_url=AUTH_FALLBACK_ROUTE,
                        sign_up_fallback_redirect_url=AUTH_FALLBACK_ROUTE,
                    ),
                    login_explanation(),
                    align="center",
                    spacing="4",
                    width="100%",
                ),
                min_height="100vh",
                padding="1em",
            ),
            sign_in_url=SIGN_IN_ROUTE,
            sign_in_fallback_redirect_url=AUTH_FALLBACK_ROUTE,
            sign_up_fallback_redirect_url=AUTH_FALLBACK_ROUTE,
        ),
        appearance="light",
        has_background=True,
    )
