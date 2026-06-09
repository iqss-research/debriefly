from dotenv import load_dotenv
import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex import styles
from debriefly.reflex.form_designer import style
from pathlib import Path

# from debriefly.reflex.views.analyze import main as analyze_main
from debriefly.reflex.backend.backend import MainState

load_dotenv()


def _split_markdown_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    intro_lines: list[str] = []
    current_lines: list[str] = []
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    in_code_block = False

    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block

        if not in_code_block and line.startswith("## "):
            if current_title is None:
                intro_lines = current_lines
            else:
                sections.append((current_title, "\n".join(current_lines).strip()))

            current_title = line[3:].strip()
            current_lines = []
            continue

        current_lines.append(line)

    if current_title is None:
        return markdown.strip(), []

    sections.append((current_title, "\n".join(current_lines).strip()))
    return "\n".join(intro_lines).strip(), sections


def _markdown_component_map() -> dict:
    text_color = rx.color("gray", 12)

    return {
        "h1": lambda text: rx.heading(
            text,
            as_="h1",
            size=rx.breakpoints(initial="7", xs="8", sm="9"),
            weight="bold",
            color=text_color,
            line_height="1.08",
            margin_top="0",
            margin_bottom="0.5em",
            overflow_wrap="anywhere",
        ),
        "h2": lambda text: rx.heading(
            text,
            as_="h2",
            size=rx.breakpoints(initial="5", sm="6"),
            weight="bold",
            color=text_color,
            line_height="1.2",
            margin_top="0",
            margin_bottom="0.5em",
            overflow_wrap="anywhere",
        ),
        "h3": lambda text: rx.heading(
            text,
            as_="h3",
            size=rx.breakpoints(initial="4", sm="5"),
            weight="medium",
            color=text_color,
            line_height="1.25",
            margin_top="0.8em",
            margin_bottom="0.45em",
            overflow_wrap="anywhere",
        ),
        "p": lambda text: rx.text(
            text,
            as_="p",
            size=rx.breakpoints(initial="3", sm="4"),
            color=text_color,
            line_height="1.7",
            margin_y="0.85em",
            overflow_wrap="break-word",
            width="100%",
        ),
        "ol": lambda text: rx.ordered_list(
            text,
            margin_y="0.75em",
            padding_left=["1.25rem", "1.5rem"],
        ),
        "ul": lambda text: rx.unordered_list(
            text,
            margin_y="0.75em",
            padding_left=["1.25rem", "1.5rem"],
        ),
        "li": lambda text: rx.list_item(
            text,
            margin_y="0.45em",
            overflow_wrap="break-word",
        ),
        "a": lambda text, **props: rx.link(
            text,
            **props,
            color=styles.accent_text_color,
            font_weight="bold",
            overflow_wrap="anywhere",
            text_decoration="underline",
            text_decoration_color=styles.accent_text_color,
        ),
        "code": lambda text: rx.code(
            text,
            color_scheme="gray",
            max_width="100%",
            overflow_wrap="anywhere",
            white_space="pre-wrap",
        ),
        "codeblock": lambda text, **props: rx.code_block(
            text,
            **props,
            font_size="0.82rem",
            margin_y="1em",
            max_width="100%",
            overflow_x="auto",
            width="100%",
            wrap_long_lines=True,
        ),
    }


def _index_section(
    section: tuple[str, str], index: int, markdown_components: dict
) -> rx.Component:
    title, content = section
    section_text_color = rx.color("gray", 12)

    return rx.accordion.item(
        header=rx.hstack(
            rx.heading(
                title,
                size=rx.breakpoints(initial="3", xs="4"),
                weight="medium",
                color=section_text_color,
                line_height="1.25",
                overflow_wrap="break-word",
            ),
            align="center",
            justify="between",
            width="100%",
            color=section_text_color,
        ),
        content=rx.box(
            rx.markdown(
                content,
                component_map=markdown_components,
            ),
            color=section_text_color,
            overflow_x="auto",
            padding_top="0.75rem",
            padding_bottom="0.25rem",
            width="100%",
        ),
        value=f"index-section-{index}",
        border=styles.border,
        border_radius=styles.border_radius,
        color=section_text_color,
        padding=["0.75rem", "0.75rem 1rem"],
        margin_bottom="0.75rem",
        background_color=rx.color("gray", 2),
        width="100%",
    )


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
    intro, sections = _split_markdown_sections(index_content.read_text())

    markdown_components = _markdown_component_map()

    return style.layout(
        rx.image(
            src="/debriefly-logo.png",
            alt="Debriefly",
            width=["min(100%, 15rem)", "min(100%, 22rem)", "min(100%, 30rem)"],
            height="auto",
            margin_bottom="1rem",
        ),
        rx.box(
            rx.markdown(
                intro,
                component_map=markdown_components,
            ),
            max_width="100%",
            overflow_x="hidden",
            width="100%",
        ),
        rx.accordion.root(
            *[
                _index_section(section, index, markdown_components)
                for index, section in enumerate(sections)
            ],
            collapsible=True,
            default_value=[],
            show_dividers=False,
            type="multiple",
            width="100%",
        ),
        align="start",
        spacing="4",
        width="100%",
    )


# @rx.page(route="/analyze/[q_id]", title="Answer", on_load=[MainState.init])
# @template
# def analyze() -> rx.Component:
#     return analyze_main()
