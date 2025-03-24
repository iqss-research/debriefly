import reflex as rx
from pathlib import Path
from debriefly.reflex.form_designer import style
from debriefly.reflex.backend.backend import MainState

@rx.page(
    route="/terms",
    title="Terms of Service",
    on_load=MainState.init,
)
def terms_of_service() -> rx.Component:
    terms_content = Path(__file__).resolve().parent.parent.parent / "reflex/pages/terms_of_service.md"

    markdown_styles = {
        "h2": {
            "margin_bottom": "0.5em",  # Reduce space after h2
        },
        "h3": {
            "margin_top": "0.5em",     # Reduce space before h3
            "margin_bottom": "0.5em",  # Reduce space after h3
        },
        "ol": {
            "margin_top": "0.5em",     # Control list spacing
        }
    }

    return style.layout(
        rx.markdown(
            terms_content.read_text(),
            custom_styles=markdown_styles,
        )
    )