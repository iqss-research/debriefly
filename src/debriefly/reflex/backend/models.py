from datetime import datetime, timezone, timedelta
import secrets
from typing import Optional
from sqlmodel import Field
import reflex as rx
from enum import Enum as PyEnum
import sqlmodel
import json
from reflex.utils.serializers import serializer
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import OperationalError
from debriefly.openai import DEFAULT_OPENAI_MODEL


def _new_public_id() -> str:
    return secrets.token_urlsafe(16)


class Config(rx.Model, table=True):
    section: str
    name: str
    value: str

    @classmethod
    def get_config(cls, session, which):
        config = session.exec(sqlmodel.select(cls).where(Config.name == which)).first()
        return config.value


class User(rx.Model, table=True):
    __table_args__ = (
        UniqueConstraint(
            "email_normalized",
            name="uq_user_email_normalized",
        ),
    )

    user_id: str = Field(primary_key=True)
    email_normalized: str | None = None
    email_verified_at: datetime | None = None
    status: str = "active"
    role: str = "user"
    auth_version: int = 1
    created_at: datetime | None = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=True,
        ),
    )
    updated_at: datetime | None = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=True,
        ),
    )
    tos_version: str | None = None
    tos_accepted_at: datetime | None = None


class UserIdentity(rx.Model, table=True):
    """Map an external identity to Debriefly's stable internal user ID."""

    __tablename__ = "user_identity"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "issuer",
            "subject",
            name="uq_user_identity_provider_issuer_subject",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            "issuer",
            name="uq_user_identity_user_provider_issuer",
        ),
    )

    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    user_id: str = sqlmodel.Field(
        foreign_key="user.user_id",
        index=True,
        ondelete="CASCADE",
    )
    provider: str = "clerk"
    issuer: str
    subject: str
    email: str | None = None
    email_normalized: str | None = None
    email_verified_at: datetime | None = None
    link_source: str = "import"
    created_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=False,
        ),
    )


class LocalCredential(rx.Model, table=True):
    """Local login material, deliberately separate from serialized User state."""

    __tablename__ = "local_credential"

    user_id: str = sqlmodel.Field(
        primary_key=True,
        foreign_key="user.user_id",
        ondelete="CASCADE",
    )
    # NULL means the imported user must consume a password-setup token.
    password_hash: str | None = sqlmodel.Field(
        default=None,
        sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=True),
    )
    password_changed_at: datetime | None = None
    failed_attempts: int = 0
    locked_until: datetime | None = None


class AuthSession(rx.Model, table=True):
    """Revocable server-side session; only a digest of the cookie is stored."""

    __tablename__ = "auth_session"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_auth_session_token_digest"),
    )

    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    user_id: str = sqlmodel.Field(
        foreign_key="user.user_id",
        index=True,
        ondelete="CASCADE",
    )
    token_digest: str
    auth_version: int
    created_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=False,
        ),
    )
    last_seen_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=False,
        ),
    )
    expires_at: datetime = sqlmodel.Field(index=True)
    revoked_at: datetime | None = None


class AuthToken(rx.Model, table=True):
    """One-time email verification, password setup, or reset token."""

    __tablename__ = "auth_token"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_auth_token_token_digest"),
    )

    id: int | None = sqlmodel.Field(default=None, primary_key=True)
    user_id: str = sqlmodel.Field(
        foreign_key="user.user_id",
        index=True,
        ondelete="CASCADE",
    )
    purpose: str
    token_digest: str
    email_normalized: str | None = None
    created_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(
            sqlmodel.DateTime(timezone=True),
            nullable=False,
        ),
    )
    expires_at: datetime = sqlmodel.Field(index=True)
    used_at: datetime | None = None


class UserOpenAISettings(rx.Model, table=True):
    __tablename__ = "user_openai_settings"

    user_id: str = Field(primary_key=True, foreign_key="user.user_id")
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL

    @classmethod
    def _ensure_table(cls, session):
        cls.__table__.create(session.get_bind(), checkfirst=True)

    @classmethod
    def get_for_user(cls, session, user_id: str | None):
        if not user_id:
            return None
        try:
            return session.get(cls, user_id)
        except OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            session.rollback()
            cls._ensure_table(session)
            return None

    @classmethod
    def get_for_form(cls, session, form_id: int | str | None):
        if form_id in (None, ""):
            return None
        form = session.get(Form, int(form_id))
        if form is None:
            return None
        return cls.get_for_user(session, form.user_id)

    @property
    def is_configured(self) -> bool:
        return bool((self.api_key or "").strip())


class FieldType(PyEnum):
    text = "text"
    checkbox = "checkbox"
    radio = "radio"
    textarea = "textarea"
    scale = "scale"
    static = "static"
    pagebreak = "pagebreak"


@serializer
def serialize_field_type(value: FieldType) -> str:
    return value.value


class Option(rx.Model, table=True):
    label: str = ""
    value: str = ""

    field_id: int = sqlmodel.Field(foreign_key="field.id")


class BundleItem(rx.Model, table=True):
    label: str = ""
    value: str = ""
    ordering: float = 0.0

    field_id: int = sqlmodel.Field(foreign_key="field.id")


class Field(rx.Model, table=True):
    name: str = ""
    type_: FieldType = FieldType.text
    required: bool = False
    bundled: bool = False
    debriefing: bool = False
    # Retained only for compatibility with the existing migration history and
    # rollback images. Human interview behavior is not exposed by the app.
    interviewer_mode: bool = False
    allow_back: bool = False
    min_debriefing_time: Optional[int] = None
    max_debriefing_time: Optional[int] = None
    prompt: str = ""
    ordering: float = 0.0
    custom_system_message: Optional[str] = None
    custom_initial_message: Optional[str] = None
    scale_min: Optional[int] = 1
    scale_max: Optional[int] = 5

    form_id: int = sqlmodel.Field(foreign_key="form.id")
    options: list[Option] = sqlmodel.Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete",
            "order_by": "Option.id",
        },
    )
    bundle_items: list[BundleItem] = sqlmodel.Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete",
            "order_by": "BundleItem.ordering, BundleItem.id",
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
    show_submission_code: bool = False

    fields: list[Field] = sqlmodel.Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete",
            "order_by": "Field.ordering, Field.id",
        },
    )
    responses: list["Response"] = sqlmodel.Relationship(
        back_populates="form",
        sa_relationship_kwargs={"cascade": "all, delete"},
    )
    qualtrics_embed_sessions: list["QualtricsEmbedSession"] = sqlmodel.Relationship(
        back_populates="form",
        sa_relationship_kwargs={"cascade": "all, delete, delete-orphan"},
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
        # Legacy Azure Search indexing is deprecated. Analysis now reads
        # transcripts directly and uses the form owner's OpenAI API key.
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
    interview_model: str = ""
    interview_model_versions: str = ""
    interview_prompt_version: str = ""
    interview_system_prompt: str = sqlmodel.Field(
        default="", sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    interview_initial_prompt: str = sqlmodel.Field(
        default="", sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )

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


class HumanChatMessage(rx.Model, table=True):
    """Legacy storage retained for schema and rollback compatibility only."""

    __tablename__ = "human_chat_message"

    id: int = sqlmodel.Field(primary_key=True)
    field_value_id: int = sqlmodel.Field(foreign_key="fieldvalue.id", index=True)
    # role: "context" (initial context for researcher), "user" (respondent), "interviewer" (researcher)
    role: str
    content: str = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    end_chat: bool = False
    created_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(sqlmodel.DateTime(timezone=True), nullable=False),
    )


class QualtricsEmbedSession(rx.Model, table=True):
    __tablename__ = "qualtrics_embed_session"

    id: int = sqlmodel.Field(primary_key=True)
    public_id: str = sqlmodel.Field(
        default_factory=_new_public_id, index=True, nullable=False
    )
    form_id: int = sqlmodel.Field(foreign_key="form.id", ondelete="CASCADE", index=True)
    source: str = "qualtrics"
    external_response_id: str = ""
    external_question_id: str = ""
    question_text: str = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    response_text: str = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    transcript: Optional[str] = sqlmodel.Field(
        default=None, sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=True)
    )
    interview_model: str = ""
    interview_model_versions: str = ""
    interview_prompt_version: str = ""
    interview_system_prompt: str = sqlmodel.Field(
        default="", sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    interview_initial_prompt: str = sqlmodel.Field(
        default="", sa_column=sqlmodel.Column(sqlmodel.Text(), nullable=False)
    )
    completed: bool = False
    created_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(sqlmodel.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = sqlmodel.Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sqlmodel.Column(sqlmodel.DateTime(timezone=True), nullable=False),
    )

    form: Optional[Form] = sqlmodel.Relationship(
        back_populates="qualtrics_embed_sessions"
    )
