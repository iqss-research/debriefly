from dotenv import load_dotenv
import reflex as rx
from debriefly.reflex.templates import template
from debriefly.reflex.views.question_table import main_table as question_table
from debriefly.reflex.views.answer_table import main_table as answer_table
from debriefly.reflex.views.answer import main as answer_main, State as AnswerState2
from debriefly.reflex.views.analyze import main as analyze_main
from debriefly.reflex.backend.backend import State, AnswerState


load_dotenv()


@template(
    route="/",
    title="Debriefly",
    on_load=[State.load_config, State.load_profile, State.load_entries],
)
def index() -> rx.Component:
    return question_table()


@template(route="/answers/[q_id]", title="Answers", on_load=[AnswerState.load_entries])
def answers() -> rx.Component:
    return answer_table()


@template(route="/analyze/[q_id]", title="Answer")
def analyze() -> rx.Component:
    return analyze_main()


@template(route="/answer/[a_id]", title="Answer", on_load=[AnswerState2.on_load])
def answer() -> rx.Component:
    return answer_main()
