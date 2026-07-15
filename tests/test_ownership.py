from sqlmodel import Session, SQLModel, create_engine

from debriefly.reflex.backend.models import Field, FieldValue, Form, Response, User
from debriefly.reflex.components.interview.state import (
    _get_owned_interview_field_value,
)
from debriefly.reflex.form_designer.components.form_editor import (
    _get_owned_field,
    _get_owned_form,
)
from debriefly.reflex.form_designer.pages.response import _get_owned_response


def _seed_two_users(session: Session):
    owner = User(user_id="owner")
    other = User(user_id="other")
    owner_form = Form(name="Owner survey", code="owner-code", user_id=owner.user_id)
    other_form = Form(name="Other survey", code="other-code", user_id=other.user_id)
    session.add_all([owner, other, owner_form, other_form])
    session.flush()

    owner_field = Field(name="Owner question", form_id=owner_form.id)
    other_field = Field(name="Other question", form_id=other_form.id)
    owner_response = Response(client_token="owner-response", form_id=owner_form.id)
    other_response = Response(client_token="other-response", form_id=other_form.id)
    session.add_all([owner_field, other_field, owner_response, other_response])
    session.flush()

    owner_value = FieldValue(
        field_id=owner_field.id,
        response_id=owner_response.id,
        value="owner answer",
    )
    other_value = FieldValue(
        field_id=other_field.id,
        response_id=other_response.id,
        value="other answer",
    )
    session.add_all([owner_value, other_value])
    session.flush()
    ids = {
        "owner_form": owner_form.id,
        "other_form": other_form.id,
        "owner_field": owner_field.id,
        "other_field": other_field.id,
        "owner_response": owner_response.id,
        "other_response": other_response.id,
        "owner_value": owner_value.id,
        "other_value": other_value.id,
    }
    session.commit()
    return ids


def test_owned_resource_queries_reject_cross_user_ids(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ownership.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        rows = _seed_two_users(session)

        assert _get_owned_form(session, rows["owner_form"], "owner") is not None
        assert _get_owned_form(session, rows["other_form"], "owner") is None

        # A field from another account must not become editable merely because
        # the route contains a form that the current user owns.
        assert (
            _get_owned_field(
                session,
                field_id=rows["other_field"],
                form_id=rows["owner_form"],
                user_id="owner",
            )
            is None
        )
        assert (
            _get_owned_field(
                session,
                field_id=rows["owner_field"],
                form_id=rows["owner_form"],
                user_id="owner",
            )
            is not None
        )

        assert (
            _get_owned_response(
                session,
                response_id=rows["other_response"],
                form_id=rows["owner_form"],
                user_id="owner",
            )
            is None
        )
        assert (
            _get_owned_response(
                session,
                response_id=rows["owner_response"],
                form_id=rows["owner_form"],
                user_id="owner",
            )
            is not None
        )

        assert (
            _get_owned_interview_field_value(session, rows["other_value"], "owner")
            is None
        )
        assert (
            _get_owned_interview_field_value(session, rows["owner_value"], "owner")
            is not None
        )
