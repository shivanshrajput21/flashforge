from app import get_available_prompt_versions, group_cards_by_topic
from models import Difficulty, Flashcard


def test_group_cards_by_topic_preserves_indices():
    cards = [
        Flashcard(question="Q1", answer="A1", topic="Math", difficulty=Difficulty.easy),
        Flashcard(question="Q2", answer="A2", topic="History", difficulty=Difficulty.medium),
        Flashcard(question="Q3", answer="A3", topic="Math", difficulty=Difficulty.hard),
    ]

    grouped = group_cards_by_topic(cards)
    assert list(grouped.keys()) == ["Math", "History"]

    # Verify Math holds cards with original indices 0 and 2
    math_cards = grouped["Math"]
    assert len(math_cards) == 2
    assert math_cards[0][0] == 0
    assert math_cards[0][1].question == "Q1"
    assert math_cards[1][0] == 2
    assert math_cards[1][1].question == "Q3"

    # Verify History holds card with index 1
    history_cards = grouped["History"]
    assert len(history_cards) == 1
    assert history_cards[0][0] == 1
    assert history_cards[0][1].question == "Q2"


def test_get_available_prompt_versions_detects_prompts(tmp_path, monkeypatch):
    test_prompts_dir = tmp_path / "prompts"
    test_prompts_dir.mkdir()
    (test_prompts_dir / "v1.txt").write_text("prompt 1", encoding="utf-8")
    (test_prompts_dir / "v2.txt").write_text("prompt 2", encoding="utf-8")
    (test_prompts_dir / "CHANGELOG.md").write_text("notes", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    versions = get_available_prompt_versions()
    assert versions == ["v1", "v2"]
