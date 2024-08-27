import logging
from jinja2 import Environment, PackageLoader, select_autoescape
from typing import Dict
from functools import cached_property

from debriefly.qualtrics.request import QualtricsRequest
from debriefly.qualtrics.question import (
    QualtricsQuestionFactory,
    QualtricsQuestion,
    QualtricsQuestionDebriefing,
)

logger = logging.getLogger(__name__)


class QualtricsSurveyCreator(QualtricsRequest):
    endpoint = "surveys"

    def create_survey(
        self,
        name,
        survey_file=None,
        question_text=None,
        template_name="survey",
        create_version=False,
        version_description="",
        publish=True,
    ):
        assert any([survey_file, question_text]) and not all(
            [survey_file, question_text]
        ), "Exactly one of survey_file or question_text must be provided"

        if question_text is not None:
            env = Environment(
                loader=PackageLoader("debriefly.data.templates", package_path=""),
                autoescape=select_autoescape(),
            )
            template = env.get_template(f"{template_name}.jinja")
            survey_file_str = template.render(question_text=question_text)
            # Value not really important, but we need a valid filename to upload
            survey_file = "auto_generated.txt"
        else:
            survey_file_str = open(survey_file, "r").read()

        logger.debug(f"Creating survey with name {name} and file {survey_file}")
        files = {
            "file": (
                survey_file,
                survey_file_str,
                "application/vnd.qualtrics.survey.txt",
            )
        }

        self.make_request(data={"name": name}, files=files)
        survey_id = self.data["id"]
        logger.debug(f"Survey created with id {survey_id}")

        survey = QualtricsSurvey(survey_id=survey_id)
        self.survey = survey
        self.make_active()

        return survey

    def make_active(self):
        logger.debug(f"Making survey {self.survey.survey_id} active")
        self.make_request(
            method="put",
            url=f"surveys/{self.survey.survey_id}",
            json={"isActive": True},
            endpoint_override=True,
        )


class QualtricsSurvey(QualtricsRequest):
    def __init__(self, survey_id=None, data=None):
        self.survey_id = survey_id
        self.endpoint = f"surveys/{self.survey_id}"

        super().__init__(data)

        self.questions: Dict[str, QualtricsQuestion] = {
            k: QualtricsQuestionFactory(
                survey=self,
                question_type=v["questionType"]["type"],
                question_id=k,
                question_dict=v,
            )
            for k, v in self.data["questions"].items()
        }

        # populated on populate_system_message()
        self.system_message = ""
        self.initial_message = ""  # TODO: collapse into system_message?

    def __str__(self):
        return f"QualtricsSurvey (id={self.survey_id})"

    @cached_property
    def debriefing_question(self):
        return self.get_debriefing_question()

    @cached_property
    def last_question(self):
        return self.get_last_question_qualtrics()

    def get_debriefing_question_qualtrics(self, embedded_data_name="debriefly"):
        embedded_data_names = [e["name"] for e in self.data.get("embeddedData", [])]
        if embedded_data_name in embedded_data_names:
            embedded_data_index = embedded_data_names.index(embedded_data_name)

            flow = self.data.get("flow", [])
            target_block = None
            embedded_i = -1
            for block in flow:
                if block["type"] == "Block":
                    target_block = block["id"]
                if block["type"] == "EmbeddedData":
                    embedded_i += 1
                    if embedded_i == embedded_data_index:
                        break

            if target_block is None:
                logger.debug("No block preceding embedded data found.")
            else:
                logger.debug(f"Embedded data at index {embedded_i}")
                logger.debug(f"Target block = {target_block}")
                target_block_elements = self.data["blocks"][target_block]["elements"]
                target_questions = [
                    e for e in target_block_elements if e["type"] == "Question"
                ]
                if target_questions:
                    target_question_id = target_questions[-1]["questionId"]
                    logger.debug(
                        f"Debriefing question detected as {target_question_id}"
                    )
                    if target_question_id in self.questions:
                        _question = self.questions[target_question_id]
                        return QualtricsQuestionDebriefing(
                            survey=self, question=_question, response=None
                        )
                    else:
                        logger.error(f"{target_question_id} not found")
        else:
            logger.debug("No embedded data found.")

    def get_last_question_qualtrics(self):
        target_question_id = None
        flow = self.data.get("flow", [])
        for block in flow:
            if block["type"] == "Block":
                target_block = block["id"]
                target_block_elements = self.data["blocks"][target_block]["elements"]
                target_questions = [
                    e for e in target_block_elements if e["type"] == "Question"
                ]
                if target_questions:
                    target_question_id = target_questions[-1]["questionId"]

        if target_question_id is None:
            logger.error("No last question detected")
            return None

        logger.debug(f"Last question detected as {target_question_id}")
        return self.questions[target_question_id]

    def get_debriefing_question_openai(self, model="gpt-4o-mini", template_name="meta"):

        logger.debug("Determining debriefing question")
        if self.openai_client is None:
            logger.debug(
                "No OpenAI client provided; Skipping debriefing question selection."
            )
            return None

        env = Environment(
            loader=PackageLoader("debriefly.data.templates", package_path=""),
            autoescape=select_autoescape(),
        )
        template = env.get_template(f"{template_name}.jinja")
        template_str = template.render(questions=self.questions.values())

        completion = self.openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": template_str},
            ],
        )

        selected_question_id = completion.choices[0].message.content
        if selected_question_id not in self.questions:
            logger.error(f"Unexpected {selected_question_id=}")
        else:
            logger.debug(f"Debriefing question id from OpenAI = {selected_question_id}")
            _question = self.questions[selected_question_id]
            return QualtricsQuestionDebriefing(
                survey=self, question=_question, response=None
            )

    def get_debriefing_question(self):
        debriefing_question = self.get_debriefing_question_qualtrics()
        if debriefing_question is None:
            logger.debug("No debriefing question found in Qualtrics")
            debriefing_question = self.get_debriefing_question_openai()
        return debriefing_question

    def populate_system_message(self, **kwargs):
        logger.debug("Determining debriefing question")

        env = Environment(
            loader=PackageLoader("debriefly.data.templates", package_path=""),
            autoescape=select_autoescape(),
        )

        self.system_message = env.get_template("system_message.jinja").render(**kwargs)
        self.initial_message = env.get_template("initial_message.jinja").render(
            **kwargs
        )

    def chat(self, user_input, chat_history, model="gpt-4o-mini"):
        client = self.openai_client
        messages = [{"role": "system", "content": self.system_message}]
        for human_input, assistant_response in chat_history:
            if human_input is not None:
                messages.append({"role": "user", "content": human_input})
            messages.append({"role": "assistant", "content": assistant_response})
        messages.append({"role": "user", "content": user_input})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=1.0,
            stream=True,
        )

        for chunk in response:
            yield chunk.choices[0].delta.content
