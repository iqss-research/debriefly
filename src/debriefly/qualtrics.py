import gradio as gr
from json import loads
import logging
import os
import requests
from requests_oauth2client import OAuth2Client, OAuth2ClientCredentialsAuth
from jinja2 import Environment, PackageLoader, select_autoescape
from debriefly import config

logger = logging.getLogger(__name__)


class QualtricsSession:
    def __init__(
        self, data_center=None, api_token=None, client_id=None, client_secret=None
    ):
        self.data_center = data_center or os.getenv("Q_DATA_CENTER")
        assert self.data_center, "data_center is required"
        self.api_token = api_token or os.getenv("Q_API_TOKEN")

        if not self.api_token:
            client_id = client_id or os.getenv("Q_CLIENT_ID")
            client_secret = client_secret or os.getenv("Q_CLIENT_SECRET")
            assert (
                client_id and client_secret
            ), "client_id and client_secret are required"

            self.auth = OAuth2ClientCredentialsAuth(
                OAuth2Client(
                    token_endpoint=config.qualtrics.oauth2_token_endpoint,
                    client_id=client_id,
                    client_secret=client_secret,
                ),
                scope=config.qualtrics.oauth2_scope,
            )

        else:
            self.auth = None

        self.base_api_url = f"https://{data_center}.qualtrics.com/API/v3"

    def __enter__(self):
        kwargs = {"headers": {"Content-Type": "application/json"}}
        if self.api_token:
            kwargs["headers"]["x-api-token"] = self.api_token
        if self.auth:
            kwargs["auth"] = self.auth
        QualtricsRequest.default_request_kwargs = kwargs

    def __exit__(self, exc_type, exc_val, exc_tb):
        QualtricsRequest.default_request_kwargs = {}


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

    # Set by enclosing QualtricsSession context-manager
    default_request_kwargs = {}

    def __init__(self, data_center=None, api_token=None):
        data_center = data_center or os.getenv("Q_DATA_CENTER")
        assert data_center, "data_center is required"

        self.data_center = data_center
        self.api_token = api_token or os.getenv("Q_API_TOKEN")
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
            **self.default_request_kwargs,
        )
        if raise_for_status:
            response.raise_for_status()
        response = loads(response.text)

        logger.debug(
            f"{method} request: {url} json={json} kwargs={self.default_request_kwargs}"
        )
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


class QualtricsSurveySession(QualtricsRequest):
    def __init__(
        self,
        survey_id,
        data_center=None,
        api_token=None,
        openai_client=None,
        debriefing_question=None,
    ):
        super().__init__(data_center, api_token)
        self.survey_id = survey_id
        self.session_id = None
        self._questions = []
        self.done = False
        self.openai_client = openai_client

        self.survey = QualtricsSurvey(survey_id=survey_id)

        if debriefing_question == "auto":
            self.debriefing_question = self.survey.get_debriefing_question(
                client=self.openai_client
            )
        elif debriefing_question is not None:
            self.debriefing_question = self.survey.questions[debriefing_question]

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

    def submit(self, answers={}, embedded_data=None):
        url = f"surveys/{self.survey_id}/sessions/{self.session_id}"
        json = {"responses": answers}
        if embedded_data is not None:
            json["advance"] = False
            json["embeddedData"] = {"debriefly": str(embedded_data)}
        else:
            json["advance"] = not self.done

        # Detect if we're at the end of the survey, and embed the debriefing transcript
        launch_debriefing = False
        debriefing_q = self.debriefing_question
        if debriefing_q is not None and debriefing_q.question_id in answers:
            logger.info(f"{debriefing_q} found in answers. Launching debriefing.")
            launch_debriefing = True

        response = self.make_request(url, json=json)
        if not self.done:
            result = response["result"]
            self.process(result)

        return launch_debriefing

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

    def predict(self, message, history):
        history_openai_format = []
        for human, assistant in history:
            history_openai_format.append({"role": "user", "content": human})
            history_openai_format.append({"role": "assistant", "content": assistant})
        history_openai_format.append({"role": "user", "content": message})

        response = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=history_openai_format,
            temperature=1.0,
            stream=True,
        )

        partial_message = ""
        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                partial_message = partial_message + chunk.choices[0].delta.content
                yield partial_message

    def run_terminal(self):
        while not self.done:
            answers = {}
            for question in self.questions():
                answer = question.prompt()
                answers |= answer
            launch_debriefing = self.submit(answers)
            if launch_debriefing:
                print("Debriefing not supported in terminal mode.")
        print(self.done)

    def get_ui(self):
        with gr.Blocks() as ui:

            page_number_state = gr.State(0)
            launch_debriefing_state = gr.State(False)

            gr.Markdown("### Survey")
            with gr.Column():

                @gr.render(inputs=[page_number_state, launch_debriefing_state])
                def render_page(page_number, launch_debriefing):

                    boxes = []
                    if launch_debriefing:
                        chatbot = gr.Chatbot(height=200)
                        boxes.append(chatbot)
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

                    def submit_fn(page_number, is_debriefing, *box_values):
                        launch_debriefing = False
                        if is_debriefing:
                            launch_debriefing = self.submit(
                                embedded_data="debriefing transcript here!"
                            )
                        else:
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
                                            selected_id = question.choices_inv[
                                                box_value
                                            ]
                                            answer = {
                                                question.question_id: {
                                                    selected_id: {"selected": True}
                                                }
                                            }
                                        answers |= answer

                                    launch_debriefing = self.submit(answers)
                        return page_number + 1, launch_debriefing

                    next_btn.click(
                        submit_fn,
                        inputs=[page_number_state, launch_debriefing_state] + boxes,
                        outputs=[page_number_state, launch_debriefing_state],
                    )

                next_btn = gr.Button("Next")

        return ui  # caller can `ui.launch()`
