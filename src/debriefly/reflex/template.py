import reflex as rx
import reflex_clerk as clerk
from debriefly.reflex import styles
from debriefly.reflex.components.sidebar import sidebar
from debriefly.reflex.components.navbar import navbar


def menu_item_link(text, href):
    return rx.menu.item(
        rx.link(
            text,
            href=href,
            width="100%",
            color="inherit",
        ),
        _hover={
            "color": styles.accent_color,
            "background_color": styles.accent_text_color,
        },
    )


def template(page_content) -> rx.Component:
    return rx.theme(
        clerk.clerk_provider(
            clerk.protect(
                rx.flex(
                    navbar(),
                    sidebar(),
                    rx.flex(
                        rx.vstack(
                            page_content(),
                            width="100%",
                            **styles.template_content_style,
                        ),
                        width="100%",
                        **styles.template_page_style,
                        max_width=[
                            "100%",
                            "100%",
                            "100%",
                            "100%",
                            "100%",
                            styles.max_width,
                        ],
                    ),
                    flex_direction=[
                        "column",
                        "column",
                        "column",
                        "column",
                        "column",
                        "row",
                    ],
                    width="100%",
                    margin="auto",
                    position="relative",
                ),
                fallback=clerk.redirect_to_sign_in(),
            )
        ),
        appearance="light",
        has_background=True,
    )
