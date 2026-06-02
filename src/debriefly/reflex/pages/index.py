from dotenv import load_dotenv
import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.form_designer import style
from pathlib import Path

# from debriefly.reflex.views.analyze import main as analyze_main
from debriefly.reflex.backend.backend import MainState

load_dotenv()


@rx.page(
    route="/",
    title="Debriefly",
    image="/debriefly-icon.png",
    on_load=MainState.init,
)
@template
def index() -> rx.Component:
    index_content = (
        Path(__file__).resolve().parent.parent.parent / "reflex/pages/index.md"
    )

    # Custom styles for markdown content
    markdown_styles = {
        "h2": {
            "margin_bottom": "0.5em",  # Reduce space after h2
        },
        "h3": {
            "margin_top": "0.5em",  # Reduce space before h3
            "margin_bottom": "0.5em",  # Reduce space after h3
        },
        "ol": {
            "margin_top": "0.5em",  # Control list spacing
        },
    }

    return style.layout(
        rx.image(
            src="/debriefly-logo.png",
            alt="Debriefly",
            width=["min(100%, 18rem)", "min(100%, 24rem)", "min(100%, 34rem)"],
            height="auto",
            margin_bottom="1rem",
        ),
        rx.markdown(
            index_content.read_text(),
            custom_styles=markdown_styles,
        ),
    )


# @rx.page(route="/analyze/[q_id]", title="Answer", on_load=[MainState.init])
# @template
# def analyze() -> rx.Component:
#     return analyze_main()
