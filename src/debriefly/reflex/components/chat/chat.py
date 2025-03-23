import reflex as rx
from debriefly.reflex.components.chat.loading_icon import loading_icon
from debriefly.reflex.components.chat.state import QA, ChatState
from reflex_chakra import form as chakra_form, form_control as chakra_form_control

message_style = dict(
    display="inline-block",
    padding="1em",
    border_radius="8px",
    max_width=["30em", "30em", "50em", "50em", "50em", "50em"],
)

def message(qa: QA) -> rx.Component:
    return rx.box(
        rx.cond(
            qa.question != "",
            rx.box(
                rx.markdown(
                    qa.question,
                    background_color=rx.color("mauve", 4),
                    color=rx.color("mauve", 12),
                    **message_style,
                ),
                text_align="right",
                margin_top="1em",
            ),
        ),
        rx.box(
            rx.markdown(
                qa.answer,
                background_color=rx.color("accent", 4),
                color=rx.color("accent", 12),
                **message_style,
            ),
            text_align="left",
            padding_top="1em",
        ),
        width="100%",
    )

def chat() -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.foreach(ChatState.chat, message),
            width="100%",
        ),
        py="8",
        flex="1",
        width="100%",
        padding_x="4px",
        align_self="center",
        overflow="hidden",
        padding_bottom="5em",
    )

def action_bar() -> rx.Component:
    return rx.center(
        rx.vstack(
            # Conditionally show the message based on show_finish
            rx.cond(
                ChatState.show_finish,
                rx.box(
                    rx.text(
                        "Now, you can finish your conversation. You are of course more than welcome to keep the conversation.",
                        color="green"
                    ),
                    id="finish_message",
                    padding="0.5em",
                    background_color="lightgreen",
                    border_radius="4px",
                    margin_bottom="8px",
                    width="100%",
                ),
                rx.fragment(),  # Empty when hidden
            ),
            chakra_form(
                chakra_form_control(
                    rx.hstack(
                        rx.clipboard(
                            rx.input(
                                rx.input.slot(
                                    rx.tooltip(
                                        rx.icon("info", size=18),
                                        content="Enter your answer here",
                                    )
                                ),
                                placeholder="Type something...",
                                id="question",
                                width=["15em", "20em", "45em", "50em", "50em", "50em"],
                            ),
                            on_paste=rx.prevent_default,
                        ),
                        rx.button(
                            rx.cond(
                                ChatState.processing,
                                loading_icon(height="1em"),
                                rx.text("Send"),
                            ),
                            type="submit",
                        ),
                        # Conditionally show the Finish Chat button based on show_finish
                        rx.cond(
                            ChatState.show_finish,
                            rx.button(
                                "Finish Chat",
                                id="finish_chat_button",
                                on_click=ChatState.finish_chat,
                            ),
                            rx.fragment(),  # Empty when hidden
                        ),
                        align_items="center",
                        spacing="2",
                    ),
                    is_disabled=ChatState.processing,
                ),
                on_submit=ChatState.process_question,
                reset_on_submit=True,
            ),
            align_items="center",
            width="100%",
        ),
        position="sticky",
        bottom="0",
        left="0",
        padding_y="16px",
        backdrop_filter="auto",
        backdrop_blur="lg",
        border_top=f"1px solid {rx.color('mauve', 3)}",
        background_color=rx.color('mauve', 2),
        align_items="stretch",
        width="100%",
    )

def chat_ui() -> rx.Component:
    return rx.cond(
        ~ChatState.loaded,
        rx.spinner(),
        rx.cond(
            ChatState.done,
            rx.spinner(),
            rx.vstack(
                chat(),
                action_bar(),
                rx.script("""
                    if (!window.timerInterval) {
                        function checkAndActivateFinish() {
                            const chatElement = document.getElementById('chat_ui');
                            if (!chatElement) {
                                clearInterval(window.timerInterval);
                                window.timerInterval = null;
                                return;
                            }
                            try {
                                window.reflex.call("ChatState.check_min_time_reached").then(() => {
                                    window.reflex.updateState();
                                });
                            } catch (e) {
                                console.error("Error checking time:", e);
                            }
                        }
                        
                        checkAndActivateFinish();
                        
                        window.timerInterval = setInterval(checkAndActivateFinish, 1000);
                        
                        window.addEventListener('beforeunload', function() {
                            if (window.timerInterval) {
                                clearInterval(window.timerInterval);
                                window.timerInterval = null;
                            }
                        });
                    }
                """),
                # Disabling the timer (it is for debugging purposes)
                #rx.cond(
                #    ChatState.show_timer,
                #    rx.cond(
                #        ~ChatState.show_finish,
                #        rx.text(
                #            f"Time remaining: {ChatState.time_remaining // 60} min {ChatState.time_remaining % 60} sec",
                #            color="gray.600",
                #            font_size="sm",
                #            text_align="center",
                #            width="100%",
                #            margin_top="8px",
                #        ),
                #    ),
                #),
                id="chat_ui",  # Add this line
                height="100%",
            ),
        ),
    )