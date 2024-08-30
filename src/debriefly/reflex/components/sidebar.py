import reflex as rx
import reflex_clerk as clerk
from debriefly import __version__
from .. import styles


def clerk_navbar() -> rx.Component:
    return rx.vstack(
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


def info_footer() -> rx.Component:
    return rx.vstack(clerk_navbar(), rx.text(f"{__version__}", width="100%"))


def sidebar_item_icon(icon: str) -> rx.Component:
    return rx.icon(icon, size=18)


def sidebar_item(text: str, url: str) -> rx.Component:
    # Whether the item is active.
    active = (rx.State.router.page.path == url.lower()) | (
        (rx.State.router.page.path == "/") & text == "Overview"
    )

    return rx.link(
        rx.hstack(
            rx.match(
                text,
                ("Overview", sidebar_item_icon("home")),
                ("Profile", sidebar_item_icon("user")),
                sidebar_item_icon("layout-dashboard"),
            ),
            rx.text(text, size="3", weight="regular"),
            color=rx.cond(
                active,
                styles.accent_text_color,
                styles.text_color,
            ),
            style={
                "_hover": {
                    "background_color": rx.cond(
                        active,
                        styles.accent_bg_color,
                        styles.gray_bg_color,
                    ),
                    "color": rx.cond(
                        active,
                        styles.accent_text_color,
                        styles.text_color,
                    ),
                    "opacity": "1",
                },
                "opacity": rx.cond(
                    active,
                    "1",
                    "0.95",
                ),
            },
            align="center",
            border_radius=styles.border_radius,
            width="100%",
            spacing="2",
            padding="0.35em",
        ),
        underline="none",
        href=url,
        width="100%",
    )


def sidebar() -> rx.Component:
    # Get all the decorated pages and add them to the sidebar.
    from reflex.page import get_decorated_pages

    # The ordered page routes.
    ordered_page_routes = ["/", "/profile"]

    # Get the decorated pages.
    pages = get_decorated_pages()

    # Include all pages even if they are not in the ordered_page_routes.
    ordered_pages = sorted(
        pages,
        key=lambda page: (
            ordered_page_routes.index(page["route"])
            if page["route"] in ordered_page_routes
            else len(ordered_page_routes)
        ),
    )

    return rx.flex(
        rx.vstack(
            rx.heading("Debriefly", align="left"),
            rx.vstack(
                *[
                    sidebar_item(
                        text=page.get("title", page["route"].strip("/").capitalize()),
                        url=page["route"],
                    )
                    for page in ordered_pages
                ],
                spacing="1",
                width="100%",
            ),
            rx.spacer(),
            rx.divider(),
            info_footer(),
            justify="end",
            align="start",
            width=styles.sidebar_content_width,
            height="100dvh",
            padding="1em",
        ),
        display=["none", "none", "none", "none", "none", "flex"],
        max_width=styles.sidebar_width,
        width="auto",
        height="100%",
        position="sticky",
        justify="end",
        top="0px",
        left="0px",
        flex="1",
        bg=rx.color("gray", 2),
    )
