import reflex as rx

from debriefly.reflex import styles
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.components.sidebar import mobile_sidebar, sidebar


def menu_item_link(text, href):
    return rx.menu.item(
        rx.link(text, href=href, width="100%", color="inherit"),
        _hover={
            "color": styles.accent_color,
            "background_color": styles.accent_text_color,
        },
    )


def template(page_content) -> rx.Component:
    layout = rx.box(
        mobile_sidebar(),
        rx.flex(
            sidebar(),
            rx.flex(
                rx.vstack(
                    page_content(),
                    width="100%",
                    **styles.template_content_style,
                ),
                flex="1 1 auto",
                min_width="0",
                width="100%",
                **styles.template_page_style,
                max_width=["100%"],
            ),
            align="stretch",
            min_height="100dvh",
            width="100%",
        ),
        width="100%",
    )
    return rx.theme(
        rx.cond(
            MainState.is_authenticated,
            layout,
            rx.center(rx.spinner(size="3"), min_height="100vh"),
        ),
        appearance="light",
        has_background=True,
    )
