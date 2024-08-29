from dotenv import load_dotenv
import reflex as rx
from ..templates import template
from ..views.table import main_table
from ..views.chat import chat_gen_ui
from ..backend.backend import State


load_dotenv()


@template(route="/", title="Overview", on_load=[State.load_entries, State.load_profile])
def index() -> rx.Component:
    return rx.hstack(main_table(), chat_gen_ui())
