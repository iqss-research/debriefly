import reflex as rx
from pathlib import Path
from debriefly.reflex.form_designer import style


@rx.page(
    route="/privacy",
    title="Privacy Statement",
)
def privacy_statement() -> rx.Component:
    privacy_content = (
        Path(__file__).resolve().parent.parent.parent
        / "reflex/pages/privacy_statement.md"
    )

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
        rx.markdown(
            privacy_content.read_text(),
            custom_styles=markdown_styles,
        )
    )
