from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlmodel import Field
import reflex as rx
from enum import Enum as PyEnum
import sqlmodel
import json
from reflex.utils.serializers import serializer
from debriefly.openai import AzureOpenAISearch


class Config(rx.Model, table=True):
    section: str
    name: str
    value: str

    @classmethod
    def get_config(cls, session, which):
        config = session.exec(sqlmodel.select(cls).where(Config.name == which)).first()
        return config.value


class User(rx.Model, table=True):
    user_id: str = Field(primary_key=True)
    qualtrics_api_token: Optional[str] = None


class FieldType(PyEnum):
    text = "text"
    checkbox = "checkbox"
    radio = "radio"
    textarea = "textarea"
    static = "static"
    pagebreak = "pagebreak"


@serializer
def serialize_field_type(value: FieldType) -> str:
    return value.value


class Option(rx.Model, table=True):
    label: str = ""
    value: str = ""

    field_id: int = sqlmodel.Field(foreign_key="field.id")


class Field(rx.Model, table=True):
    name: str = ""
    type_: FieldType = FieldType.text
    required: bool = False
    debriefing: bool = False
    min_debriefing_time: Optional[int] = None
    prompt: str = ""
    ordering: float = 0.0

    form_id: int = sqlmodel.Field(foreign_key="form.id")
    options: list[Option] = sqlmodel.Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete",
            "order_by": "Option.id",
        },
    )
    field_values: list["FieldValue"] = sqlmodel.Relationship(
        back_populates="field",
        sa_relationship_kwargs={
            "cascade": "all, delete, delete-orphan",
        },
    )


class Form(rx.Model, table=True):
    name: str = ""
    code: str = ""
    user_id: str = sqlmodel.Field(foreign_key="user.user_id")
    show_submission_code: bool = sqlmodel.Field(default=False)

    fields: list[Field] = sqlmodel.Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete",
            "order_by": "Field.ordering",
        },
    )
    responses: list["Response"] = sqlmodel.Relationship(
        back_populates="form",
        sa_relationship_kwargs={"cascade": "all, delete"},
    )
    indexed_ts: datetime = sqlmodel.Field(
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            server_default=sqlmodel.func.now(),
        ),
    )
    user: Optional[User] = sqlmodel.Relationship()

    @property
    def index_name(self):
        return f"debriefly-{self.id}"

    def index_is_current(self):
        # Is the index current and doesn't need updating?
        last_indexed = self.indexed_ts
        return all([last_indexed > response.ts for response in self.responses])

    def index_is_available(self):
        # Is the index ready for querying?
        last_indexed = self.indexed_ts
        return datetime.now(last_indexed.tzinfo) > last_indexed + timedelta(minutes=2)

    def index(self):
        with rx.session() as session:
            client = AzureOpenAISearch(
                index_name=self.index_name,
                api_key=Config.get_config(session, "AZURE_OPENAI_API_KEY"),
                api_version=Config.get_config(session, "AZURE_OPENAI_API_VERSION"),
                api_endpoint=Config.get_config(session, "AZURE_OPENAI_ENDPOINT"),
                api_model=Config.get_config(session, "AZURE_OPENAI_DEPLOYMENT_MODEL"),
                search_key=Config.get_config(session, "AZURE_OPENAI_SEARCH_KEY"),
                search_endpoint=Config.get_config(
                    session, "AZURE_OPENAI_SEARCH_ENDPOINT"
                ),
            )
            client.delete_index()
            client.upload(self.debriefing_transcripts())
            self.indexed_ts = datetime.now(timezone.utc)

    def debriefing_transcripts(self) -> dict[str, str]:
        transcripts = {}
        for response in self.responses:
            txt = ""
            for field_value in response.field_values:
                if field_value.debriefing:
                    messages = json.loads(field_value.debriefing)
                    for message in messages:
                        txt += message["role"] + ": " + message["content"] + "\n\n"
            if txt:
                transcripts[response.client_token] = txt
        return transcripts


class FieldValue(rx.Model, table=True):
    field_id: int = sqlmodel.Field(foreign_key="field.id")
    response_id: int = sqlmodel.Field(foreign_key="response.id")
    value: str
    debriefing: Optional[str]

    field: Field = sqlmodel.Relationship(sa_relationship_kwargs={"lazy": "selectin"})


class Response(rx.Model, table=True):
    id: int = sqlmodel.Field(primary_key=True)
    client_token: str
    form_id: int = sqlmodel.Field(foreign_key="form.id")
    ts: datetime = sqlmodel.Field(
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            server_default=sqlmodel.func.now(),
        ),
    )
    form: Form = sqlmodel.Relationship(back_populates="responses")

    field_values: list[FieldValue] = sqlmodel.Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete"}
    )
