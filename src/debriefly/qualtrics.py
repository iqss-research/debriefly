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

        # populated on populate_system_message()
        self.system_message = ""
        self.initial_message = ""  # TODO: collapse into system_message?

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

    def populate_system_message(self, client, **kwargs):
        logger.info("Determining debriefing question")
        if client is None:
            raise RuntimeError("No OpenAI client provided")

        env = Environment(
            loader=PackageLoader("debriefly.data.templates", package_path=""),
            autoescape=select_autoescape(),
        )

        self.system_message = env.get_template("system_message.jinja").render(**kwargs)
        self.initial_message = env.get_template("initial_message.jinja").render(
            **kwargs
        )

    def chat(self, client, user_input, chat_history, model="gpt-4o-mini"):
        messages = [{"role": "system", "content": self.system_message}]
        for human_input, assistant_response in chat_history:
            if human_input is not None:
                messages.append({"role": "user", "content": human_input})
            messages.append({"role": "assistant", "content": assistant_response})
        messages.append({"role": "user", "content": user_input})

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=1.0,
            stream=False,
        )

        return completion.choices[0].message.content


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

        debriefing_q_a = {}
        debriefing_q = self.debriefing_question
        if debriefing_q is not None and debriefing_q.question_id in answers:
            logger.info(f"Debriefing Question: {debriefing_q} found in answers.")
            debriefing_q_a[debriefing_q] = answers[debriefing_q.question_id]

        response = self.make_request(url, json=json)
        if not self.done:
            result = response["result"]
            self.process(result)

        return debriefing_q_a

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
            debriefing_q_a = self.submit(answers)
            if debriefing_q_a:
                print("Debriefing not supported in terminal mode.")
        print(self.done)

    def chat(self, user_input, chat_history):
        completion = self.survey.chat(self.openai_client, user_input, chat_history)
        return "", chat_history + [(user_input, completion)]

    def check_chat_end(
        self,
        chat_history: list[list[str | None]],
        limit: int = 4,
        end_of_interview: str = "<end_of_survey>",
    ) -> tuple[list[list[str | None]], gr.Button, gr.Textbox, gr.Button]:
        done = False
        if len(chat_history) >= limit:
            done = True
        if end_of_interview in chat_history[-1][1]:
            chat_history[-1][1] = chat_history[-1][1].replace(end_of_interview, "")
            done = True

        logger.info("Done with chat.")
        input_textbox = gr.Textbox(visible=not done, show_label=False)
        submit_button = gr.Button(
            "Submit",
            variant="primary",
            visible=not done,
        )
        return chat_history, input_textbox, submit_button, done

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
                            self.openai_client, question=question, response=response
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
