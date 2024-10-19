from datetime import datetime
from typing import Optional
from sqlmodel import Field
import reflex as rx
from enum import Enum as PyEnum
import sqlmodel
from reflex.utils.serializers import serializer


class Config(rx.Model, table=True):
    section: str
    name: str
    value: str


class User(rx.Model, table=True):
    user_id: str = Field(primary_key=True)
    qualtrics_api_token: Optional[str] = None
    qualtrics_client_id: Optional[str] = None
    qualtrics_client_secret: Optional[str] = None
    qualtrics_data_center: Optional[str] = None


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
    prompt: str = ""
    ordering: float = 0.0

    form_id: int = sqlmodel.Field(foreign_key="form.id")
    options: list[Option] = sqlmodel.Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete"},
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
    user: Optional[User] = sqlmodel.Relationship()


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
