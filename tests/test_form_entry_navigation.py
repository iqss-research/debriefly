from debriefly.reflex.backend.models import Field, FieldType
from debriefly.reflex.form_designer.pages.form_entry import FormEntryTabState


def make_field(
    id_: int,
    type_: FieldType = FieldType.text,
    *,
    debriefing: bool = False,
    allow_back: bool = False,
) -> Field:
    field = Field(
        form_id=1,
        name=f"field_{id_}",
        type_=type_,
        debriefing=debriefing,
        allow_back=allow_back,
        ordering=float(id_),
    )
    field.id = id_
    return field


def split_ids(fields: list[Field]) -> tuple[list[list[int]], list[bool]]:
    tabs, back_enabled = FormEntryTabState.split_fields_into_tabs(fields)
    return [[field.id for field in tab] for tab in tabs], back_enabled


def test_page_break_can_enable_back_for_next_page():
    page_ids, back_enabled = split_ids(
        [
            make_field(1),
            make_field(2, FieldType.pagebreak, allow_back=True),
            make_field(3),
        ]
    )

    assert page_ids == [[1], [3]]
    assert back_enabled == [False, True]


def test_page_break_defaults_to_forward_only():
    page_ids, back_enabled = split_ids(
        [
            make_field(1),
            make_field(2, FieldType.pagebreak),
            make_field(3),
        ]
    )

    assert page_ids == [[1], [3]]
    assert back_enabled == [False, False]


def test_debriefing_split_is_forward_only():
    page_ids, back_enabled = split_ids(
        [
            make_field(1, debriefing=True),
            make_field(2),
        ]
    )

    assert page_ids == [[1], [2]]
    assert back_enabled == [False, False]


def test_page_break_after_debriefing_stays_forward_only():
    page_ids, back_enabled = split_ids(
        [
            make_field(1, debriefing=True),
            make_field(2, FieldType.pagebreak, allow_back=True),
            make_field(3),
        ]
    )

    assert page_ids == [[1], [3]]
    assert back_enabled == [False, False]


def test_debriefing_question_page_can_go_back_when_previous_page_break_allows_it():
    tabs, back_enabled = FormEntryTabState.split_fields_into_tabs(
        [
            make_field(1),
            make_field(2, FieldType.pagebreak, allow_back=True),
            make_field(3, debriefing=True),
        ]
    )

    assert [[field.id for field in tab] for tab in tabs] == [[1], [3]]
    assert back_enabled == [False, True]
    assert FormEntryTabState.tab_can_go_back(tabs, back_enabled, 1)
