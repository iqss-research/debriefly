from dotenv import load_dotenv
import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.views.question_table import main_table as question_table
from debriefly.reflex.views.answer_table import main_table as answer_table
from debriefly.reflex.views.answer import main as answer_main, State as AnswerState2
from debriefly.reflex.views.analyze import main as analyze_main
from debriefly.reflex.backend.backend import MainState, AnswerState

load_dotenv()


@rx.page(route="/", title="Debriefly", on_load=[MainState.init])
@template
def index() -> rx.Component:
    return rx.vstack(
        rx.heading("Welcome to Debriefly"),
        rx.text("This is an app under constuction.."),
    )


@rx.page(
    route="/questions",
    title="Debriefly",
    on_load=[MainState.init],
)
@template
def questions() -> rx.Component:
    return question_table()


@rx.page(
    route="/answers/[q_id]",
    title="Answers",
    on_load=[MainState.init, AnswerState.load_entries],
)
@template
def answers() -> rx.Component:
    return answer_table()


@rx.page(route="/analyze/[q_id]", title="Answer", on_load=[MainState.init])
@template
def analyze() -> rx.Component:
    return analyze_main()


@rx.page(
    route="/answer/[a_id]",
    title="Answer",
    on_load=[MainState.init, AnswerState2.on_load],
)
@template
def answer() -> rx.Component:
    return answer_main()
