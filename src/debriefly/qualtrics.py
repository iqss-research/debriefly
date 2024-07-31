import gradio as gr
from json import loads
import logging
import os
import requests


logger = logging.getLogger(__name__)


class QualtricsQuestion:
    def __init__(self, question):
        self.question_type = question["type"]
        self.question_id = question["questionId"]
        self.display = question["display"]
        self.choices = question.get("choices", [])
        self.choices_inv = {
            choice["display"]: choice["choiceId"] for choice in self.choices
        }

    def __str__(self):
        match self.question_type:
            case "mc":
                choices = "; ".join(
                    [
                        choice["choiceId"] + ":" + choice["display"]
                        for choice in self.choices
                    ]
                )
                return f"{self.display} (mcq)" + f"\nChoices: {choices}"
            case "te":
                return f"{self.display} (text)"
            case _:
                return f"{self.display} ({self.question_type})"

    def prompt(self):
        print(self)
        match self.question_type:
            case "mc":
                answer = input("Enter your choice index: ")
                return {self.question_id: {answer: {"selected": True}}}
            case "te":
                answer = input("Enter your answer: ")
                return {self.question_id: answer}
            case _:
                raise NotImplementedError


class QualtricsRequest:
    def __init__(self, data_center=None, api_token=None):
        self.data_center = data_center or os.environ["Q_DATA_CENTER"]
        self.api_token = api_token or os.environ["Q_API_TOKEN"]
        self.base_url = f"https://{data_center}.qualtrics.com/API/v3"

    def make_request(self, url, json={}, raise_for_status=False):
        url = f"{self.base_url}/{url}"
        response = requests.post(
            url,
            json=json,
            headers={"x-api-token": self.api_token, "Content-Type": "application/json"},
        )
        if raise_for_status:
            response.raise_for_status()
        response = loads(response.text)

        logger.debug(f"post request: {url} json={json}")
        logger.debug(f"post response: {response}")

        return response


class QualtricsSession(QualtricsRequest):
    def __init__(self, survey_id, data_center=None, api_token=None):
        super().__init__(data_center, api_token)
        self.survey_id = survey_id
        self.session_id = None
        self._questions = []
        self.done = False

    def questions(self):
        if self.done:
            raise StopIteration
        if self.session_id is None:
            self.start_session()

        return self._questions

    def start_session(self):
        url = f"surveys/{self.survey_id}/sessions"
        response = self.make_request(url)
        result = response["result"]
        self.session_id = result["sessionId"]
        self.process(result)

    def submit(self, answers):
        url = f"surveys/{self.survey_id}/sessions/{self.session_id}"
        json = {"advance": False if self.done else True, "responses": answers}
        response = self.make_request(url, json=json)
        if not self.done:
            result = response["result"]
            self.process(result)

    def process(self, result):
        self._questions = [QualtricsQuestion(q) for q in result["questions"]]
        self.done = result["done"]

    def run_terminal(self):
        while not self.done:
            answers = {}
            for question in self.questions():
                answer = question.prompt()
                answers |= answer
            self.submit(answers)
        print(self.done)

    def get_ui(self):
        with gr.Blocks() as ui:

            page_number_state = gr.State(0)

            gr.Markdown("### Survey")
            with gr.Column():

                @gr.render(inputs=[page_number_state])
                def render_page(page_number):
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
                                        label=f"Question {question.question_id}: {question.display}",
                                        value="",
                                        lines=5,
                                        interactive=True,
                                    )
                                else:
                                    new_txtbox = gr.Radio(
                                        label=f"Question {question.question_id}: {question.display}",
                                        choices=[
                                            choice["display"]
                                            for choice in question.choices
                                        ],
                                        interactive=True,
                                    )

                                boxes.append(new_txtbox)

                    def submit_fn(page_number, *box_values):
                        if page_number == 0:
                            self.start_session()
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
                                        selected_id = question.choices_inv[box_value]
                                        answer = {
                                            question.question_id: {
                                                selected_id: {"selected": True}
                                            }
                                        }
                                    answers |= answer

                                self.submit(answers)
                        return page_number + 1

                    next_btn.click(
                        submit_fn,
                        inputs=[page_number_state] + boxes,
                        outputs=page_number_state,
                    )

                next_btn = gr.Button("Next")

        return ui  # caller can `ui.launch()`
