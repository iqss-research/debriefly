import json

from debriefly.reflex.backend.models import BundleItem, Field, FieldType, Option
from debriefly.reflex.components.chat.state import _bundle_response_context
from debriefly.reflex.form_designer.pages.form_entry import (
    bundle_field_input_name,
    bundle_option_input_name,
    bundled_item_response,
)
from debriefly.reflex.form_designer.pages.response import bundle_answer_map


def make_bundle_field() -> Field:
    field = Field(
        name="trust",
        type_=FieldType.scale,
        bundled=True,
        prompt="How much do you believe the following institution?",
        form_id=1,
    )
    field.id = 1
    bank = BundleItem(label="Bank", value="bank", ordering=1.0, field_id=1)
    bank.id = 1
    government = BundleItem(
        label="Government", value="government", ordering=2.0, field_id=1
    )
    government.id = 2
    field.bundle_items = [bank, government]
    return field


def test_bundle_field_input_name_uses_stable_item_value():
    field = make_bundle_field()

    assert bundle_field_input_name(field, field.bundle_items[0]) == "trust___1"


def test_bundle_answer_map_reads_saved_json():
    raw_value = json.dumps(
        [
            {"label": "Bank", "value": "bank", "response": "4"},
            {"label": "Government", "value": "government", "response": "2"},
        ]
    )

    assert bundle_answer_map(raw_value) == {"bank": "4", "government": "2"}


def test_bundle_response_context_formats_prompt_context():
    field = make_bundle_field()
    raw_value = json.dumps(
        [
            {"label": "Bank", "value": "bank", "response": "4"},
            {"label": "Government", "value": "government", "response": "2"},
        ]
    )

    response_text, subquestions, subquestions_text = _bundle_response_context(
        field, raw_value
    )

    assert response_text == "Bank: 4\nGovernment: 2"
    assert subquestions_text == response_text
    assert subquestions == [
        {"label": "Bank", "value": "bank", "response": "4"},
        {"label": "Government", "value": "government", "response": "2"},
    ]


def test_bundled_radio_response_uses_shared_option_label():
    field = make_bundle_field()
    field.type_ = FieldType.radio
    option = Option(label="A lot", value="4", field_id=field.id)
    option.id = 10
    field.options = [option]

    response = bundled_item_response(
        field,
        field.bundle_items[0],
        {bundle_field_input_name(field, field.bundle_items[0]): "4"},
    )

    assert response == "A lot"


def test_bundled_checkbox_response_uses_shared_option_labels():
    field = make_bundle_field()
    field.type_ = FieldType.checkbox
    first = Option(label="Trust", value="trust", field_id=field.id)
    first.id = 10
    second = Option(label="Distrust", value="distrust", field_id=field.id)
    second.id = 11
    field.options = [first, second]

    response = bundled_item_response(
        field,
        field.bundle_items[0],
        {
            bundle_option_input_name(field, field.bundle_items[0], first): "trust",
            bundle_option_input_name(field, field.bundle_items[0], second): "distrust",
        },
    )

    assert response == "Trust, Distrust"
