import reflex as rx
import reflex_clerk as clerk
from debriefly import __version__
from debriefly.reflex import styles
from debriefly.reflex.form_designer.components.form_select import (
    FormSelectState,
    form_select,
)
from debriefly.reflex.form_designer import routes

# from debriefly.reflex.form_designer.components.form_editor import FormEditorState
import uuid
from debriefly.reflex.backend.models import Form
from debriefly.reflex.backend.backend import MainState


def info_footer() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            clerk.signed_out(
                clerk.sign_in_button(rx.button("Sign In")),
                clerk.sign_up_button(rx.button("Sign Up")),
            ),
            clerk.signed_in(
                rx.box(
                    clerk.user_button(),
                )
            ),
        ),
        rx.text(
            f"v{__version__} | ",
            rx.link(
                "Terms of Service",
                href="/terms",
                target="_blank",
                color=styles.text_color,
                _hover={"color": styles.accent_text_color},
            ),
            " | ",  # Separator
            rx.link(
                "Privacy Statement",
                href="/privacy",
                target="_blank",
                color=styles.text_color,
                _hover={"color": styles.accent_text_color},
            ),
            " | ",  # Separator
            rx.link(
                "Admin Login",
                href="/admin",
                color=styles.text_color,
                _hover={"color": styles.accent_text_color},
            ),
            size="1",  # Ensures very small font
            width="100%",
        ),
        width="100%",
    )


def sidebar_item_icon(icon: str) -> rx.Component:
    return rx.icon(icon, size=18)


def sidebar_item(text: str, url: str, icon: str) -> rx.Component:
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
            padding="0.35em 0.5em",  # Adjusted padding for consistent left alignment
        ),
        underline="none",
        href=url,
        width="100%",
    )


def _sidebar_content(
    *, height: str = "100dvh", show_heading: bool = True, close_links: bool = False
) -> rx.Component:
    def maybe_close(component: rx.Component) -> rx.Component:
        if close_links:
            return rx.drawer.close(component)
        return component

    return rx.vstack(
        *([rx.heading("Debriefly", align="left")] if show_heading else []),
        maybe_close(sidebar_item("Home", "/", "home")),
        # Create Survey section
        rx.vstack(
            rx.tooltip(
                rx.hstack(
                    rx.icon("pen", size=18),
                    rx.text("Create Survey", weight="bold"),
                    align="center",
                    spacing="2",
                    padding_left="0.5em",  # Align with sidebar items
                ),
                content="Enter New Survey Name and click 'New Survey' to create a new survey",
            ),
            rx.input(
                placeholder="Enter Survey Name",
                value=SidebarState.new_survey_name,
                on_change=SidebarState.set_new_survey_name,
                width="100%",
            ),
            rx.button(
                "New Survey",
                on_click=SidebarState.create_new_survey,
                width="100%",
                color_scheme="blue",
            ),
            spacing="1",
            width="100%",  # Ensure full width
        ),
        # Existing Surveys section
        rx.vstack(
            rx.tooltip(
                rx.hstack(
                    rx.icon("folder", size=18),
                    rx.text("Existing Surveys", weight="bold"),
                    align="center",
                    spacing="2",
                    padding_left="0.5em",  # Align with sidebar items
                ),
                content="Select your created surveys from below",
            ),
            form_select(),
            # rx.foreach(
            #    FormSelectState.forms,
            #    lambda form: rx.hstack(
            #        rx.link(
            #            rx.text(form.name),
            #            href=routes.edit_form(form.id),
            #            color=rx.cond(
            #                rx.State.form_id == form.id.to_string(),
            #                styles.accent_text_color,
            #                styles.text_color,
            #            ),
            #            width="100%",
            #        ),
            # Delete button on the sidebar. Disabled for now.
            # rx.alert_dialog.root(
            #    rx.alert_dialog.trigger(
            #        rx.button(
            #            rx.icon(
            #                tag = "delete",
            #                color = "red.500",
            #                cursor = "pointer",
            #                size=16,
            #                _hover={"color": "red.700"},
            #            ),
            #            color_scheme="tomato",
            #            on_click=SidebarState.delete_survey(form.id),
            #            variant="ghost",
            #            size="sm",
            #        ),
            #    ),
            #    rx.alert_dialog.content(
            #        rx.alert_dialog.title("Delete Survey"),
            #        rx.alert_dialog.description(
            #            "Are you sure you want to delete this survey?"
            #        ),
            #        rx.flex(
            #            rx.alert_dialog.cancel(rx.button("Cancel")),
            #            rx.spacer(),
            #            rx.alert_dialog.action(
            #                rx.button("Delete", on_click=FormEditorState.delete_form)
            #            ),
            #        ),
            #    ),
            # ),
            #        align="center",
            #        justify="between",
            #        width="100%",
            #        padding_left="0.5em",  # Align with other items
            #    ),
            # ),
            spacing="1",
            width="100%",  # Ensure full width
        ),
        maybe_close(sidebar_item("Feedback", "/feedback", "message_square")),
        maybe_close(sidebar_item("OpenAI Key", "/user", "key")),
        rx.spacer(),
        rx.divider(),
        info_footer(),
        justify="end",
        align="start",
        width="100%",  # Stretch content to full width
        height=height,
        padding="1em 0.5em",  # Adjusted padding for consistency
    )


def sidebar() -> rx.Component:
    return rx.flex(
        _sidebar_content(),
        display=["none", "none", "none", "flex"],
        width=styles.sidebar_width,  # Fixed width to match intended size
        height="100%",
        position="sticky",
        justify="start",  # Align content to the left
        top="0px",
        left="0px",
        flex="0 0 auto",
        bg=rx.color("gray", 2),  # Matches your screenshot
    )


def mobile_sidebar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.link(
                rx.hstack(
                    rx.image(
                        src="/debriefly-icon.png",
                        alt="Debriefly",
                        width="2rem",
                        height="2rem",
                    ),
                    rx.heading("Debriefly", size="4"),
                    align="center",
                    spacing="2",
                ),
                href="/",
                underline="none",
                color=styles.text_color,
            ),
            rx.drawer.root(
                rx.tooltip(
                    rx.drawer.trigger(
                        rx.button(
                            rx.icon("menu", size=22),
                            variant="ghost",
                            custom_attrs={"aria-label": "Open navigation"},
                        )
                    ),
                    content="Open navigation",
                ),
                rx.drawer.overlay(),
                rx.drawer.content(
                    rx.box(
                        rx.hstack(
                            rx.heading("Debriefly", size="4"),
                            rx.drawer.close(
                                rx.button(
                                    rx.icon("x", size=20),
                                    variant="ghost",
                                    custom_attrs={"aria-label": "Close navigation"},
                                )
                            ),
                            align="center",
                            justify="between",
                            padding="1em 0.5em 0 0.5em",
                            width="100%",
                        ),
                        _sidebar_content(
                            height="calc(100dvh - 4rem)",
                            show_heading=False,
                            close_links=True,
                        ),
                        height="100%",
                        width="100%",
                    ),
                    background_color=rx.color("gray", 2),
                    box_shadow=styles.box_shadow_style,
                    max_width="88vw",
                    overflow_y="auto",
                    right="auto",
                    width="min(20rem, 88vw)",
                ),
                direction="left",
            ),
            align="center",
            justify="between",
            width="100%",
        ),
        background_color=rx.color("gray", 2),
        border_bottom=styles.border,
        display=["block", "block", "block", "none"],
        padding="0.75rem 1rem",
        position="sticky",
        top="0",
        width="100%",
        z_index="20",
    )


class SidebarState(MainState):
    new_survey_name: str = ""

    def set_new_survey_name(self, value: str):
        self.new_survey_name = value

    async def create_new_survey(self):
        if self.new_survey_name:
            with rx.session() as session:
                new_form = Form(
                    name=self.new_survey_name,
                    user_id=self.user_id,
                    code=uuid.uuid4().hex,
                )
                session.add(new_form)
                session.commit()
                session.refresh(new_form)
            yield FormSelectState.refresh_forms
            yield rx.redirect(routes.edit_form(new_form.id))
            self.new_survey_name = ""

    async def delete_survey(self, form_id: int):
        with rx.session() as session:
            form = session.get(Form, form_id)
            if form and form.user_id == self.user_id:
                session.delete(form)
                session.commit()
            yield FormSelectState.refresh_forms
