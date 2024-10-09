from pathlib import Path
import reflex as rx
from debriefly.reflex.form_designer import style, routes


def home_page() -> rx.Component:
    readme_content = Path(__file__).resolve().parent.parent.parent / "README.md"
    return style.layout(
        rx.link("Create or Edit Survey", href=routes.FORM_EDIT_NEW),
        rx.divider(),
        rx.card(
            rx.inset(
                rx.badge(rx.code("README.md"), width="100%", size="2"),
                side="top",
                pb="current",
                clip="padding-box",
            ),
            rx.markdown(readme_content.read_text()),
            margin_y="2em",
        ),
    )
