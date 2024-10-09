import reflex as rx
import reflex_clerk as clerk
from debriefly import __version__
from debriefly.reflex import styles


pages = [
    # (Title, link, icon, clerk permission (if any) or "")
    ("Home", "/", "home", ""),
    ("Surveys", "/edit/form", "shield-question", ""),
    ("User", "/user", "user", ""),
    ("Config", "/config", "cog", "org:app:admin"),
]


def clerk_navbar() -> rx.Component:
    return rx.vstack(
        clerk.signed_out(
            clerk.sign_in_button(rx.button("Sign In")),
            clerk.sign_up_button(rx.button("Sign Up")),
        ),
        clerk.signed_in(rx.box(clerk.user_button(), clerk.organization_switcher())),
    )


def info_footer() -> rx.Component:
    return rx.vstack(clerk_navbar(), rx.text(f"{__version__}", width="100%"))


def sidebar_item_icon(icon: str) -> rx.Component:
    return rx.icon(icon, size=18)


def sidebar_item(text: str, url: str, icon: str) -> rx.Component:
    # Whether the item is active.
    active = rx.State.router.page.path == url.lower()

    return rx.link(
        rx.hstack(
            sidebar_item_icon(icon),
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
    return rx.flex(
        rx.vstack(
            rx.heading("Debriefly", align="left"),
            rx.vstack(
                *[
                    rx.cond(
                        pages[3] == "",  # no permission specified
                        sidebar_item(text=page[0], url=page[1], icon=page[2]),
                        clerk.protect(
                            sidebar_item(text=page[0], url=page[1], icon=page[2]),
                            permission=page[3],
                        ),
                    )
                    for page in pages
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
        display=["flex"],
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
