import asyncio

import pytest
import reflex as rx
from sqlmodel import Session, SQLModel, create_engine, select

import debriefly.reflex.form_designer.pages.form_entry as form_entry
from debriefly.reflex.backend.models import (
    Field,
    FieldType,
    FieldValue,
    Form,
    Option,
    Response,
    User,
)
from debriefly.reflex.form_designer.pages.form_entry import (
    FormEntryState,
    FormEntryTabState,
)


@pytest.fixture
def submission_engine(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'form-entry.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(form_entry.rx, "session", lambda: Session(engine))
    return engine


def _seed_existing_response(
    engine, *, with_debriefing: bool = False
) -> tuple[int, list[int]]:
    with Session(engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()

        fields = [
            Field(
                name=name,
                type_=FieldType.text,
                debriefing=with_debriefing and name == "second_question",
                ordering=ordering,
                form_id=form.id,
            )
            for ordering, name in enumerate(("first_question", "second_question"), 1)
        ]
        response = Response(client_token="respondent", form_id=form.id)
        session.add_all([*fields, response])
        session.flush()

        session.add_all(
            [
                FieldValue(
                    field_id=field.id,
                    response_id=response.id,
                    value=f"original {field.name}",
                )
                for field in fields
            ]
        )
        session.commit()
        return form.id, [field.id for field in fields]


def _seed_checkbox_response(engine) -> tuple[int, list[int]]:
    with Session(engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()

        checkbox = Field(
            name="choices",
            type_=FieldType.checkbox,
            ordering=1.0,
            form_id=form.id,
        )
        text = Field(
            name="note",
            type_=FieldType.text,
            ordering=2.0,
            form_id=form.id,
        )
        response = Response(client_token="respondent", form_id=form.id)
        session.add_all([checkbox, text, response])
        session.flush()

        session.add_all(
            [
                Option(label="Alpha", value="alpha", field_id=checkbox.id),
                Option(label="Beta", value="beta", field_id=checkbox.id),
                FieldValue(
                    field_id=checkbox.id,
                    response_id=response.id,
                    value="alpha",
                ),
                FieldValue(
                    field_id=checkbox.id,
                    response_id=response.id,
                    value="beta",
                ),
                FieldValue(
                    field_id=text.id,
                    response_id=response.id,
                    value="original note",
                ),
            ]
        )
        session.commit()
        return form.id, [checkbox.id, text.id]


async def _submit_page(
    engine,
    form_id: int,
    field_ids: list[int],
    values: dict[str, str],
) -> FormEntryState:
    with Session(engine) as session:
        form = session.get(Form, form_id)
        fields = [session.get(Field, field_id) for field_id in field_ids]

    root = rx.State(_reflex_internal_init=True)
    state = await root.get_state(FormEntryState)
    tab_state = await root.get_state(FormEntryTabState)
    state.client_token = "respondent"
    state.form = form
    tab_state.active_tab = 0
    tab_state.fields = [fields]

    await FormEntryState.handle_submit.fn(
        state,
        {**values, "done": "true"},
    )
    return state


def test_resubmitting_a_page_replaces_existing_field_values(submission_engine):
    form_id, field_ids = _seed_existing_response(submission_engine)

    asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {
                "first_question": "updated first answer",
                "second_question": "updated second answer",
            },
        )
    )
    asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {
                "first_question": "final first answer",
                "second_question": "final second answer",
            },
        )
    )

    with Session(submission_engine) as session:
        values = session.exec(
            select(FieldValue)
            .where(FieldValue.field_id.in_(field_ids))
            .order_by(FieldValue.field_id, FieldValue.id)
        ).all()
        responses = session.exec(
            select(Response).where(Response.client_token == "respondent")
        ).all()

    assert len(responses) == 1
    assert {value.field_id: value.value for value in values} == {
        field_ids[0]: "final first answer",
        field_ids[1]: "final second answer",
    }


def test_first_submission_creates_response_and_field_values(submission_engine):
    form_id, field_ids = _seed_existing_response(submission_engine)
    with Session(submission_engine) as session:
        response = session.exec(select(Response)).one()
        session.delete(response)
        session.commit()

    asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {
                "first_question": "first answer",
                "second_question": "second answer",
            },
        )
    )

    with Session(submission_engine) as session:
        response = session.exec(
            select(Response).where(Response.client_token == "respondent")
        ).one()
        values = session.exec(
            select(FieldValue).where(FieldValue.response_id == response.id)
        ).all()

    assert {value.field_id: value.value for value in values} == {
        field_ids[0]: "first answer",
        field_ids[1]: "second answer",
    }


def test_resubmitting_checkbox_replaces_all_selected_rows(submission_engine):
    form_id, field_ids = _seed_checkbox_response(submission_engine)
    checkbox_id, text_id = field_ids

    asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {"choices___alpha": "alpha", "note": "updated note"},
        )
    )

    with Session(submission_engine) as session:
        values = session.exec(
            select(FieldValue).where(FieldValue.field_id.in_(field_ids))
        ).all()

    assert sorted((value.field_id, value.value) for value in values) == [
        (checkbox_id, "alpha"),
        (text_id, "updated note"),
    ]

    asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {"note": "final note"},
        )
    )

    with Session(submission_engine) as session:
        values = session.exec(
            select(FieldValue).where(FieldValue.field_id.in_(field_ids))
        ).all()

    assert [(value.field_id, value.value) for value in values] == [
        (text_id, "final note")
    ]


def test_successful_submission_pins_the_debriefing_field(submission_engine):
    form_id, field_ids = _seed_existing_response(
        submission_engine, with_debriefing=True
    )

    state = asyncio.run(
        _submit_page(
            submission_engine,
            form_id,
            field_ids,
            {
                "first_question": "first answer",
                "second_question": "answer to discuss",
            },
        )
    )

    assert state.pending_debriefing_field_id == field_ids[1]
