import pytest

from app.services.llm.json_utils import parse_json_response


def test_plain_json_array():
    assert parse_json_response('[{"a": 1}]') == [{"a": 1}]


def test_strips_markdown_fence():
    assert parse_json_response('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_recovers_json_span_amid_prose():
    text = 'Here are the records:\n[{"a": 1}, {"a": 2}]\nHope that helps!'
    assert parse_json_response(text) == [{"a": 1}, {"a": 2}]


def test_raises_on_non_json():
    with pytest.raises(ValueError):
        parse_json_response("no json here")
