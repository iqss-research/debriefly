import reflex as rx
from debriefly.reflex.templates import template
from debriefly.reflex.components.chat.chat import chat_ui
from debriefly.reflex.components.chat.state import ChatState


@template(route="/chat/[a_id]", title="Chat", on_load=ChatState.on_load)
def chat() -> rx.Component:
    return chat_ui()
