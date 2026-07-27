import asyncio

import pytest
import reflex as rx
from sqlmodel import Session, SQLModel, create_engine, select

import debriefly.reflex.form_designer.components.field_editor as field_editor
from debriefly.reflex.backend.backend import MainState
from debriefly.reflex.backend.models import (
    BundleItem,
    Field,
    FieldType,
    Form,
    Option,
    User,
)
from debriefly.reflex.form_designer.components.field_editor import FieldEditorState


@pytest.fixture
def editor_engine(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'field-editor.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(field_editor.rx, "session", lambda: Session(engine))
    return engine


def _seed_form(
    engine,
    *,
    field_type: FieldType | None = None,
    bundled: bool = False,
) -> tuple[int, int | None]:
    with Session(engine) as session:
        user = User(user_id="owner")
        form = Form(name="Survey", code="survey-code", user_id=user.user_id)
        session.add_all([user, form])
        session.flush()

        field_id = None
        if field_type is not None:
            question = Field(
                name="question",
                type_=field_type,
                bundled=bundled,
                prompt="Original wording",
                ordering=3.0,
                form_id=form.id,
            )
            session.add(question)
            session.flush()
            field_id = question.id

        form_id = form.id
        session.commit()
        return form_id, field_id


async def _load_editor_state_async(
    form_id: int,
    field_id: int | None,
) -> tuple[rx.State, FieldEditorState]:
    root = rx.State(_reflex_internal_init=True)
    main_state = await root.get_state(MainState)
    state = await root.get_state(FieldEditorState)

    root.form_id = str(form_id)
    root.field_id = "new" if field_id is None else str(field_id)
    main_state._user_id = "owner"
    main_state.is_authenticated = True
    await FieldEditorState.load_field.fn(state)
    return root, state


def _load_editor_state(
    form_id: int,
    field_id: int | None,
) -> tuple[rx.State, FieldEditorState]:
    return asyncio.run(_load_editor_state_async(form_id, field_id))


@pytest.mark.parametrize("field_type", [FieldType.radio, FieldType.checkbox])
@pytest.mark.parametrize("existing", [True, False], ids=["existing", "new"])
def test_option_crud_uses_authorized_managed_field(
    editor_engine,
    field_type,
    existing,
):
    form_id, field_id = _seed_form(
        editor_engine,
        field_type=field_type if existing else None,
    )
    existing_option_id = None
    if existing:
        with Session(editor_engine) as session:
            existing_option = Option(
                label="Existing",
                value="existing",
                field_id=field_id,
            )
            session.add(existing_option)
            session.commit()
            existing_option_id = existing_option.id
    root, state = _load_editor_state(form_id, field_id)
    new_option_index = len(state.field.options)

    FieldEditorState.set_type.fn(state, field_type.value)
    FieldEditorState.set_field.fn(state, "name", "pending-name")
    FieldEditorState.set_field.fn(state, "prompt", "Pending wording")

    FieldEditorState.add_option.fn(state)

    assert root.form_id == str(form_id)
    assert state.field.id is not None
    assert state.field.name == "pending-name"
    assert state.field.prompt == "Pending wording"
    assert len(state.field.options) == new_option_index + 1

    FieldEditorState.set_option.fn(state, new_option_index, "label", "Yes")
    FieldEditorState.set_option.fn(state, new_option_index, "value", "yes")
    option_id = state.field.options[new_option_index].id

    with Session(editor_engine) as session:
        saved_field = session.get(Field, state.field.id)
        saved_option = session.get(Option, option_id)
        assert saved_field is not None
        assert saved_field.form_id == form_id
        assert saved_field.type_ == field_type
        assert saved_field.name == "pending-name"
        assert saved_field.prompt == "Pending wording"
        assert saved_option is not None
        assert (saved_option.label, saved_option.value) == ("Yes", "yes")

    FieldEditorState.delete_option.fn(state, new_option_index)

    assert len(state.field.options) == new_option_index
    with Session(editor_engine) as session:
        assert session.get(Option, option_id) is None
        if existing_option_id is not None:
            assert session.get(Option, existing_option_id) is not None


@pytest.mark.parametrize("existing", [True, False], ids=["existing", "new"])
def test_bundle_item_crud_uses_authorized_managed_field(editor_engine, existing):
    form_id, field_id = _seed_form(
        editor_engine,
        field_type=FieldType.scale if existing else None,
        bundled=existing,
    )
    existing_item_id = None
    if existing:
        with Session(editor_engine) as session:
            existing_item = BundleItem(
                label="Existing",
                value="existing",
                ordering=1.0,
                field_id=field_id,
            )
            session.add(existing_item)
            session.commit()
            existing_item_id = existing_item.id
    _, state = _load_editor_state(form_id, field_id)
    new_item_index = len(state.field.bundle_items)

    FieldEditorState.set_type.fn(state, FieldType.scale.value)
    FieldEditorState.handle_bundled_change.fn(state, True)
    FieldEditorState.set_field.fn(state, "prompt", "Pending bundled wording")

    FieldEditorState.add_bundle_item.fn(state)
    FieldEditorState.set_bundle_item.fn(state, new_item_index, "label", "Bank")
    FieldEditorState.set_bundle_item.fn(state, new_item_index, "value", "bank")
    item_id = state.field.bundle_items[new_item_index].id

    with Session(editor_engine) as session:
        saved_field = session.get(Field, state.field.id)
        saved_item = session.get(BundleItem, item_id)
        assert saved_field is not None
        assert saved_field.form_id == form_id
        assert saved_field.bundled is True
        assert saved_field.prompt == "Pending bundled wording"
        assert saved_item is not None
        assert (saved_item.label, saved_item.value) == ("Bank", "bank")

    FieldEditorState.delete_bundle_item.fn(state, new_item_index)

    assert len(state.field.bundle_items) == new_item_index
    with Session(editor_engine) as session:
        assert session.get(BundleItem, item_id) is None
        if existing_item_id is not None:
            assert session.get(BundleItem, existing_item_id) is not None


def test_child_update_rejects_field_from_another_form(editor_engine):
    owner_form_id, owner_field_id = _seed_form(
        editor_engine,
        field_type=FieldType.radio,
    )
    with Session(editor_engine) as session:
        other = User(user_id="other")
        other_form = Form(name="Other survey", code="other-code", user_id=other.user_id)
        session.add_all([other, other_form])
        session.flush()
        other_field = Field(type_=FieldType.radio, form_id=other_form.id)
        session.add(other_field)
        session.commit()
        other_field_id = other_field.id

    _, state = _load_editor_state(owner_form_id, owner_field_id)
    state.field.id = other_field_id

    FieldEditorState.add_option.fn(state)

    with Session(editor_engine) as session:
        options = session.exec(select(Option)).all()
        assert options == []
