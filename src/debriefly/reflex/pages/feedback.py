import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.backend.backend import MainState


# Simple function to open mail client with pre-filled email
def open_email_client():
    return rx.redirect("mailto:knakamura@g.harvard.edu?subject=Debriefly%20Feedback")


def open_github_issues():
    return rx.redirect("https://github.com/yourusername/debriefly/issues")


@rx.page(route="/feedback", title="Feedback", on_load=[MainState.init])
@template
def feedback_page() -> rx.Component:
    """Render the feedback page."""
    return rx.box(
        rx.vstack(
            rx.heading("Feedback", size="lg", margin_bottom="1em"),
            rx.text(
                "We welcome your feedback, comments, suggestions, code contributions, and bug reports. "
                "You can contribute to debriefly by:",
                margin_bottom="1em",
            ),
            # Using ordered list for numbered items with custom styling
            rx.ordered_list(
                # First item with Github link
                rx.list_item(
                    rx.hstack(
                        rx.text(
                            "Submitting bug reports and feature requests on Github Issues"
                        ),
                    ),
                    # Add custom styling to make the marker (number) bold
                    css={"& > ::marker": {"font-weight": "bold"}},
                ),
                # Second item with clickable email
                rx.list_item(
                    rx.hstack(
                        rx.text("Emailing the maintainer"),
                        rx.link(
                            "(Kentaro Nakamura)",
                            href="https://k-nakam.github.io/",
                            color="blue.500",
                            is_external=True,
                        ),
                    ),
                    # Add custom styling to make the marker (number) bold
                    css={"& > ::marker": {"font-weight": "bold"}},
                ),
                # Apply styling to all list items
                spacing="1em",
                margin_left="1.5em",
            ),
            # Simplified buttons in horizontal layout
            rx.hstack(
                rx.link(
                    rx.tooltip(
                        rx.button(
                            "GitHub Issues",
                            color_scheme="purple",
                            size="md",
                        ),
                        content="Open GitHub Issue Page",
                    ),
                    href="https://github.com/iqss-research/debriefly/issues",
                    is_external=True,
                    text_decoration="none",
                ),
                rx.link(
                    rx.tooltip(
                        rx.button(
                        "Email Feedback",
                        color_scheme="green",
                        size="md",
                        ),
                        content="Email to the Maintainer",
                    ),
                    href="mailto:knakamura@g.harvard.edu?subject=Debriefly%20Feedback",
                    text_decoration="none",
                ),
                spacing="4",
                margin_top="1em",
                align_items="center",
            ),
            width="100%",
            align_items="flex_start",  # Left-align the content
            spacing="4",
        ),
        width="100%",
        max_width="800px",
        margin="0 auto",
        padding="2em",
    )
