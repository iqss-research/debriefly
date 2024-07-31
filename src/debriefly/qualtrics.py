import gradio as gr
from json import loads
import logging
import os
import requests
from jinja2 import Environment, PackageLoader, select_autoescape

logger = logging.getLogger(__name__)


class QualtricsQuestion:
    def __init__(
        self, question_type, question_id, question_text, choices={}, choices_inv={}
    ):
        self.question_type = question_type
        self.question_id = question_id
        self.question_text = question_text
        self.choices = choices
        self.choices_inv = choices_inv

    @classmethod
    def from_dict(cls, question_id, question_dict):
        choices = {
            k: v["choiceText"] for k, v in question_dict.get("choices", {}).items()
        }
        return cls(
            question_type=question_dict["questionType"]["type"],
            question_id=question_id,
            question_text=question_dict["questionText"],
            choices=choices,
            choices_inv={v: k for k, v in choices.items()},
        )

    def __str__(self):
        match self.question_type:
            case "mc":
                choices = "; ".join(
                    [
                        choice["choiceId"] + ":" + choice["display"]
                        for choice in self.choices
                    ]
                )
                return f"{self.question_text} (mcq)" + f"\nChoices: {choices}"
            case "te":
                return f"{self.question_text} (text)"
            case _:
                return f"{self.question_text} ({self.question_type})"

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

    def make_request(self, url, json={}, method="post", raise_for_status=False):
        match method:
            case "get":
                request_fn = requests.get
            case "post":
                request_fn = requests.post
            case _:
                raise NotImplementedError

        url = f"{self.base_url}/{url}"
        response = request_fn(
            url,
            json=json,
            headers={"x-api-token": self.api_token, "Content-Type": "application/json"},
        )
        if raise_for_status:
            response.raise_for_status()
        response = loads(response.text)

        logger.debug(f"{method} request: {url} json={json}")
        logger.debug(f"{method} response: {response}")

        return response


class QualtricsSurvey(QualtricsRequest):
    def __init__(self, survey_id, data_center=None, api_token=None):
        super().__init__(data_center, api_token)
        self.survey_id = survey_id

        url = f"surveys/{self.survey_id}"
        response = self.make_request(url, method="get")

        # mapping from question_id to QualtricsQuestion
        self.questions = {
            k: QualtricsQuestion.from_dict(k, v)
            for k, v in response["result"]["questions"].items()
        }

    def get_debriefing_question(
        self, client, model="gpt-4o-mini", template_name="meta"
    ):

        logger.info("Determining debriefing question")
        if client is None:
            logger.info(
                "No OpenAI client provided; Skipping debriefing question selection."
            )
            return None

        env = Environment(
            loader=PackageLoader("debriefly.data.templates", package_path=""),
            autoescape=select_autoescape(),
        )
        template = env.get_template(f"{template_name}.jinja")
        template_str = template.render(questions=self.questions.values())

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": template_str},
            ],
        )

        selected_question_id = completion.choices[0].message.content
        if selected_question_id not in self.questions:
            logger.error(f"Unexpected {selected_question_id=}")
        else:
            logger.info(f"Debriefing question = {selected_question_id}")
            return self.questions[selected_question_id]


class QualtricsSession(QualtricsRequest):
    def __init__(
        self, survey_id, data_center=None, api_token=None, openapi_client=None
    ):
        super().__init__(data_center, api_token)
        self.survey_id = survey_id
        self.session_id = None
        self._questions = []
        self.done = False

        self.survey = QualtricsSurvey(survey_id=survey_id)
        self.debriefing_question = self.survey.get_debriefing_question(
            client=openapi_client
        )

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

        # Detect if we're at the end of the survey, and embed the debriefing transcript
        if self.debriefing_question.question_id in answers:
            json |= {
                "embeddedData": {
                    "debriefly": "debriefing transcript for "
                    + answers[self.debriefing_question.question_id]
                }
            }

        response = self.make_request(url, json=json)
        if not self.done:
            result = response["result"]
            self.process(result)

    def process(self, result):
        self._questions = []
        for q in result["questions"]:
            choices = q.get("choices", {})
            choices_inv = {c["display"]: c["choiceId"] for c in choices}
            qualtrics_question = QualtricsQuestion(
                question_type=q["type"],
                question_id=q["questionId"],
                question_text=q["display"],
                choices=choices,
                choices_inv=choices_inv,
            )
            self._questions.append(qualtrics_question)
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
