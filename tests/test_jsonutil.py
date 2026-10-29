import pytest

from app.jsonutil import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_json():
    text = '```json\n{"document_type": "bill", "amounts": ["10"]}\n```'
    assert extract_json(text) == {"document_type": "bill", "amounts": ["10"]}


def test_think_block_is_stripped():
    text = '<think>the user wants JSON... {"hidden": true}</think>{"a": 1}'
    assert extract_json(text) == {"a": 1}


def test_prose_around_json():
    text = 'Sure! Here is the result:\n{"issuer": "BESCOM"}\nHope that helps.'
    assert extract_json(text) == {"issuer": "BESCOM"}


def test_no_json_raises():
    with pytest.raises(ValueError, match="No JSON object found"):
        extract_json("I cannot help with that.")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        extract_json("")
