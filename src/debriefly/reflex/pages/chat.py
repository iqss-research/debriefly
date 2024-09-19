import reflex as rx
from debriefly.reflex.templates import template
from debriefly.reflex.components.chat.chat import chat_ui
from debriefly.reflex.components.chat.state import State


@template(route="/chat/[answer_id]", title="Chat", on_load=State.on_load)
def chat() -> rx.Component:
    return chat_ui()
