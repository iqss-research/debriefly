from dotenv import load_dotenv
import reflex as rx
from debriefly.reflex.template import template

# from debriefly.reflex.views.analyze import main as analyze_main
from debriefly.reflex.backend.backend import MainState

load_dotenv()


@rx.page(route="/", title="Debriefly", on_load=[MainState.init])
@template
def index() -> rx.Component:
    return rx.vstack(
        rx.heading("Welcome to Debriefly"),
        rx.text("This is an app under constuction.."),
    )


# @rx.page(route="/analyze/[q_id]", title="Answer", on_load=[MainState.init])
# @template
# def analyze() -> rx.Component:
#     return analyze_main()
