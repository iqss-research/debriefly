from debriefly.reflex.backend.models import Field
from debriefly.reflex.form_designer.components.form_editor import FormEditorState


def make_field(id_: int, ordering: float) -> Field:
    field = Field(form_id=1, ordering=ordering)
    field.id = id_
    return field


def ordered_ids(fields: list[Field]) -> list[int]:
    return [field.id for field in FormEditorState._ordered_fields(fields)]


def orderings(fields: list[Field]) -> list[float]:
    return [field.ordering for field in FormEditorState._ordered_fields(fields)]


def test_move_field_up_renumbers_duplicate_orderings():
    fields = [make_field(1, 1.0), make_field(2, 1.0), make_field(3, 2.0)]

    assert FormEditorState._move_field(fields, 2, -1)

    assert ordered_ids(fields) == [2, 1, 3]
    assert orderings(fields) == [1.0, 2.0, 3.0]


def test_move_field_down_renumbers_duplicate_orderings():
    fields = [make_field(1, 1.0), make_field(2, 1.0), make_field(3, 2.0)]

    assert FormEditorState._move_field(fields, 1, 1)

    assert ordered_ids(fields) == [2, 1, 3]
    assert orderings(fields) == [1.0, 2.0, 3.0]


def test_next_field_ordering_uses_max_existing_ordering():
    fields = [make_field(1, 1.0), make_field(2, 1.0), make_field(3, 4.0)]

    assert FormEditorState._next_field_ordering(fields) == 5.0
