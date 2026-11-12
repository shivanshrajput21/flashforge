from models import Difficulty, Flashcard
from utils import deduplicate


def _make_card(question: str, answer: str = "Sample answer.") -> Flashcard:
    return Flashcard(
        question=question,
        answer=answer,
        topic="Testing",
        difficulty=Difficulty.easy,
    )


def test_deduplicate_removes_exact_normalized_matches():
    cards = [
        _make_card("What is HTTP?"),
        _make_card("  what   is   http? "),
        _make_card("How does DNS resolution work?"),
    ]
    result = deduplicate(cards)
    assert [c.question for c in result] == [
        "What is HTTP?",
        "How does DNS resolution work?",
    ]


def test_deduplicate_removes_near_duplicates_with_difflib():
    cards = [
        _make_card("What is the time complexity of binary search?"),
        _make_card("What is the time complexity of a binary search?"),
        _make_card("How does quicksort partition an array?"),
    ]
    result = deduplicate(cards, threshold=0.85)
    assert len(result) == 2
    assert result[0].question == "What is the time complexity of binary search?"
    assert result[1].question == "How does quicksort partition an array?"


def test_deduplicate_respects_custom_threshold():
    cards = [
        _make_card("What is Python?"),
        _make_card("What is Cython?"),
    ]
    # With a very strict/high threshold (0.99), these are kept as distinct.
    assert len(deduplicate(cards, threshold=0.99)) == 2
    # With a lower threshold (0.80), the second is dropped as similar.
    assert len(deduplicate(cards, threshold=0.80)) == 1

