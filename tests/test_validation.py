import json
import pytest
from generator import parse_and_validate, strip_code_fences
from models import Difficulty


def test_strip_code_fences():
    # JSON with markdown tag
    wrapped_json = '```json\n[{"question": "Q?", "answer": "A."}]\n```'
    assert strip_code_fences(wrapped_json) == '[{"question": "Q?", "answer": "A."}]'

    # Plain fences without language tag
    wrapped_plain = '```\n[{"question": "Q?", "answer": "A."}]\n```'
    assert strip_code_fences(wrapped_plain) == '[{"question": "Q?", "answer": "A."}]'

    # Unfenced raw string
    raw = '[{"question": "Q?", "answer": "A."}]'
    assert strip_code_fences(raw) == raw


def test_parse_and_validate_fenced_json():
    raw = """```json
    [
      {
        "question": "What is paging?",
        "answer": "A memory management scheme allocating non-contiguous physical memory.",
        "topic": "OS",
        "difficulty": "medium"
      }
    ]
    ```"""
    cards, dropped = parse_and_validate(raw)
    assert len(cards) == 1
    assert dropped == 0
    assert cards[0].question == "What is paging?"
    assert cards[0].difficulty == Difficulty.medium


def test_parse_and_validate_plain_text_before_or_after_raises_json_error():
    # Text surrounding the JSON array is malformed JSON syntax and should raise JSONDecodeError
    surrounded = 'Here are your flashcards:\n[{"question": "Q?", "answer": "A.", "difficulty": "easy"}]\nHope this helps!'
    with pytest.raises(json.JSONDecodeError):
        parse_and_validate(surrounded)


def test_parse_and_validate_invalid_json_raises():
    invalid_syntax = '[{"question": "Broken json", "answer": }]'
    with pytest.raises(json.JSONDecodeError):
        parse_and_validate(invalid_syntax)


def test_parse_and_validate_drops_blank_question_and_long_answer():
    fifty_words = "word " * 50
    raw = f"""[
      {{"question": "Valid Question?", "answer": "Short valid answer.", "topic": "Tech", "difficulty": "easy"}},
      {{"question": "   ", "answer": "Has blank question.", "topic": "Tech", "difficulty": "easy"}},
      {{"question": "Overly long answer?", "answer": "{fifty_words}", "topic": "Tech", "difficulty": "hard"}}
    ]"""
    cards, dropped = parse_and_validate(raw)
    assert len(cards) == 1
    assert dropped == 2
    assert cards[0].question == "Valid Question?"


def test_parse_and_validate_json_object_instead_of_list_raises_value_error():
    # Returning a single JSON object instead of an array
    obj_raw = '{"question": "Single card?", "answer": "Not inside a list.", "difficulty": "easy"}'
    with pytest.raises(ValueError, match="Expected a JSON list"):
        parse_and_validate(obj_raw)


def test_parse_and_validate_normalizes_missing_topic_and_capitalized_difficulty():
    raw = """[
      {
        "question": "What is an inode?",
        "answer": "A data structure representing a filesystem object.",
        "difficulty": "Easy"
      }
    ]"""
    cards, dropped = parse_and_validate(raw)
    assert len(cards) == 1
    assert dropped == 0
    # Missing topic normalized to "General"
    assert cards[0].topic == "General"
    # "Easy" normalized to Difficulty.easy
    assert cards[0].difficulty == Difficulty.easy
