import reflex as rx
from ..templates import template
from ..components.chat import chat as c


@template(route="/chat", title="Chat")
def chat() -> rx.Component:

    return rx.vstack(
        c.title_bar(survey_id="1234"),
        c.chat(),
        c.action_bar(),
        background_color=rx.color("mauve", 1),
        color=rx.color("mauve", 12),
        min_height="100vh",
        align_items="stretch",
        spacing="0",
    )
