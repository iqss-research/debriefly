import reflex as rx
from debriefly.reflex.template import template
from debriefly.reflex.components.chat.chat import chat_ui
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.components.chat.state import ChatState


@rx.page(route="/chat", title="Chat", on_load=[MainState.init, ChatState.on_load])
@template
def chat() -> rx.Component:
    return chat_ui()
