from dotenv import load_dotenv
import reflex as rx
import reflex_clerk as clerk
import reflex_clerk.clerk_client
from .views.navbar import navbar
from .views.chat import chat_gen_ui
from .views.table import main_table
from .backend.backend import State


load_dotenv()


def index() -> rx.Component:
    return clerk.clerk_provider(
        clerk.protect(
            rx.vstack(
                navbar(),
                rx.flex(
                    rx.box(main_table(), width=["100%", "100%", "100%", "60%"]),
                    chat_gen_ui(),
                    spacing="6",
                    width="100%",
                    flex_direction=["column", "column", "column", "row"],
                ),
                height="100vh",
                bg=rx.color("accent", 1),
                width="100%",
                spacing="6",
                padding_x=["1.5em", "1.5em", "3em"],
                padding_y=["1em", "1em", "2em"],
            ),
            fallback=clerk.redirect_to_sign_in(),
        )
    )


app = rx.App(
    theme=rx.theme(
        appearance="light", has_background=True, radius="large", accent_color="blue"
    ),
)
reflex_clerk.install_pages(app)

app.add_page(
    index,
    on_load=State.load_entries,
    title="Debriefly",
    description="Debriefly speaking, it does very little.",
)
