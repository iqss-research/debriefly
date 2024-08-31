import reflex as rx
from debriefly.reflex.templates import template
from debriefly.reflex.components.chat.chat import chat_ui


@template(route="/chat", title="Chat")
def chat() -> rx.Component:
    return chat_ui()
