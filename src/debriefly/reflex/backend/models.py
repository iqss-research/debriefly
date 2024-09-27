from typing import List, Optional
from datetime import datetime
import sqlmodel
import sqlalchemy as sa
import reflex as rx


class Config(rx.Model, table=True):
    section: str
    name: str
    value: str


class Profile(rx.Model, table=True):
    user_id: str = sqlmodel.Field(primary_key=True)
    qualtrics_api_token: Optional[str] = None
    qualtrics_client_id: Optional[str] = None
    qualtrics_client_secret: Optional[str] = None
    qualtrics_data_center: Optional[str] = None


class Question(rx.Model, table=True):
    user_id: str = sqlmodel.Field(foreign_key="profile.user_id")
    question_text: str
    created_on: datetime | None = sqlmodel.Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.func.now()},
        nullable=False,
    )
    modified_on: datetime | None = sqlmodel.Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"onupdate": sa.func.now(), "server_default": sa.func.now()},
    )

    answers: List["Answer"] = sqlmodel.Relationship(
        back_populates="question",
        sa_relationship_kwargs={"lazy": "selectin"},
        cascade_delete=True,
    )

    def debriefing_transcripts(self):
        return [answer.debriefing for answer in self.answers]


class Answer(rx.Model, table=True):
    user_id: str = sqlmodel.Field(foreign_key="profile.user_id")
    question_id: int = sqlmodel.Field(foreign_key="question.id")
    answer: str
    debriefing: str = None
    created_on: datetime | None = sqlmodel.Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.func.now()},
        nullable=False,
    )
    modified_on: datetime | None = sqlmodel.Field(
        default=None,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"onupdate": sa.func.now(), "server_default": sa.func.now()},
    )

    question: Optional["Question"] = sqlmodel.Relationship(back_populates="answers")
