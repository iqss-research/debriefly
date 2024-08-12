import gradio as gr
import logging

logger = logging.getLogger(__name__)


class QualtricsSurveySessionUI:
    def __init__(self, survey_session):
        self.survey_session = survey_session

    def get_ui(self):
        with gr.Blocks() as ui:

            page_number_state = gr.State(0)
            launch_debriefing_state = gr.State({})
            just_done_debriefing_state = gr.State(False)

            gr.Markdown("### Survey")
            with gr.Column():

                @gr.render(inputs=[page_number_state, launch_debriefing_state])
                def render_page(page_number, launch_debriefing):

                    boxes = []
                    if launch_debriefing:
                        logger.info("Launching Debriefing.")
                        question, response = launch_debriefing.popitem()
                        self.survey.populate_system_message(
                            question=question, response=response
                        )
                        chatbot = gr.Chatbot(
                            value=[(None, self.survey.initial_message)], height=400
                        )
                        user_input = gr.Textbox(visible=True, show_label=False)
                        submit_btn = gr.Button(
                            "Submit", variant="primary", visible=True
                        )
                        submit_btn.click(
                            self.chat, [user_input, chatbot], [user_input, chatbot]
                        ).then(
                            self.check_chat_end,
                            inputs=[chatbot],
                            outputs=[
                                chatbot,
                                user_input,
                                submit_btn,
                                just_done_debriefing_state,
                            ],
                        )

                        boxes.extend([chatbot, user_input, submit_btn])
                    else:
                        if page_number <= 0:
                            boxes = [
                                gr.Textbox(
                                    label="",
                                    value="Click on Next to begin",
                                    interactive=False,
                                )
                            ]
                        else:
                            if self.done:
                                boxes = [
                                    gr.Textbox(
                                        label="Survey Completed",
                                        value=f"{self.done}",
                                        lines=2,
                                        interactive=False,
                                    )
                                ]
                            else:
                                boxes = []
                                for question in self.questions():
                                    if question.question_type == "te":
                                        new_txtbox = gr.Textbox(
                                            label=f"Question {question.question_id}: {question.question_text}",
                                            value="",
                                            lines=5,
                                            interactive=True,
                                        )
                                    else:
                                        new_txtbox = gr.Radio(
                                            label=f"Question {question.question_id}: {question.question_text}",
                                            choices=[
                                                choice["display"]
                                                for choice in question.choices
                                            ],
                                            interactive=True,
                                        )

                                    boxes.append(new_txtbox)

                    def submit_fn(page_number, just_done_debriefing, *box_values):
                        debriefing_q_a = {}
                        if just_done_debriefing:
                            # Ugly!
                            transcript = "\n\n".join(
                                [
                                    "\n".join([str(x[0]), str(x[1])])
                                    for x in box_values[0]
                                ]
                            )

                            logger.info("Debriefing completed.")
                            _ = self.submit(embedded_data=transcript)
                        else:
                            if page_number == 0:
                                self.session.start()
                            else:
                                if not self.done:
                                    answers = {}
                                    for question, box_value in zip(
                                        self.questions(), box_values
                                    ):
                                        if question.question_type == "te":
                                            answer = {question.question_id: box_value}
                                            answers |= answer
                                        else:
                                            selected_id = question.choices_inv[
                                                box_value
                                            ]
                                            answer = {
                                                question.question_id: {
                                                    selected_id: {"selected": True}
                                                }
                                            }
                                        answers |= answer

                                    debriefing_q_a = self.submit(answers)

                        return page_number + 1, debriefing_q_a, False

                    next_btn.click(
                        submit_fn,
                        inputs=[page_number_state, just_done_debriefing_state] + boxes,
                        outputs=[
                            page_number_state,
                            launch_debriefing_state,
                            just_done_debriefing_state,
                        ],
                    )

                next_btn = gr.Button("Next")

        return ui  # caller can `ui.launch()`
