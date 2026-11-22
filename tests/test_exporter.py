import csv
from pathlib import Path
import pytest

from exporter import (
    export_anki,
    export_csv,
    list_decks,
    load_deck,
    log_metrics,
    sanitize_deck_name,
    save_deck,
)
from models import Difficulty, Flashcard, RunMetrics


def _sample_cards() -> list[Flashcard]:
    return [
        Flashcard(
            question='What is "ACID"?',
            answer="Atomicity, Consistency, Isolation,\nand Durability.",
            topic="Database Systems",
            difficulty=Difficulty.easy,
        ),
        Flashcard(
            question="Explain, with commas, what a transaction is.",
            answer="A logical unit of work, containing one or more SQL statements.",
            topic="Database Systems",
            difficulty=Difficulty.medium,
        ),
    ]


def test_export_csv_escapes_commas_quotes_and_newlines():
    cards = _sample_cards()
    csv_text = export_csv(cards)

    # Read back using csv.reader to verify RFC-compliant structure
    reader = list(csv.reader(csv_text.splitlines()))
    assert reader[0] == ["question", "answer", "topic", "difficulty"]
    assert len(reader) == 3
    # Check quotes escaping
    assert reader[1][0] == 'What is "ACID"?'
    # Check newline preservation within CSV cell
    assert "Atomicity, Consistency, Isolation," in reader[1][1]
    # Check comma escaping in question
    assert reader[2][0] == "Explain, with commas, what a transaction is."


def test_export_anki_format_and_headers():
    cards = _sample_cards()
    anki_text = export_anki(cards)
    lines = anki_text.strip().split("\n")

    # Header check
    assert lines[0] == "#separator:tab"
    assert lines[1] == "#html:false"
    assert lines[2] == "#tags column:3"

    # Data rows: exactly 3 tab-separated fields
    row1 = lines[3].split("\t")
    assert len(row1) == 3
    assert row1[0] == 'What is "ACID"?'
    # Newlines inside answer should be converted to single spaces
    assert "\n" not in row1[1]
    assert "Atomicity, Consistency, Isolation, and Durability." in row1[1]
    # Tag should have spaces replaced with underscores
    assert row1[2] == "Database_Systems easy"


def test_save_and_load_deck_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("exporter.DECKS_DIR", tmp_path / "decks")
    cards = _sample_cards()

    saved_path = save_deck("My Test Deck", cards, prompt_version="v2")
    assert saved_path.is_file()
    assert saved_path.name == "My_Test_Deck.json"

    loaded_deck = load_deck("My Test Deck")
    assert loaded_deck.name == "My_Test_Deck"
    assert loaded_deck.prompt_version == "v2"
    assert len(loaded_deck.cards) == len(cards)
    assert loaded_deck.cards[0].question == cards[0].question
    assert loaded_deck.cards[1].answer == cards[1].answer

    # Verify list_decks
    decks = list_decks()
    assert decks == ["My_Test_Deck"]


def test_sanitize_deck_name():
    assert sanitize_deck_name("biology/chapter:1*test? ") == "biology_chapter_1_test"
    assert sanitize_deck_name("../../../secrets") == "secrets"
    assert sanitize_deck_name("   ") == "deck"


def test_load_deck_missing_or_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("exporter.DECKS_DIR", tmp_path / "decks")

    with pytest.raises(FileNotFoundError):
        load_deck("nonexistent_deck")

    # Invalid JSON file
    (tmp_path / "decks").mkdir(parents=True, exist_ok=True)
    corrupt_file = tmp_path / "decks" / "corrupted.json"
    corrupt_file.write_text("Not valid json {{{", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse deck"):
        load_deck("corrupted")


def test_log_metrics_writes_header_once(tmp_path):
    metrics_path = tmp_path / "metrics.csv"
    m1 = RunMetrics(
        prompt_version="v1",
        chunks=2,
        first_try_failures=1,
        retries=1,
        failed_parses=1,
        api_failures=0,
        cards_kept=5,
        cards_dropped=1,
    )
    m2 = RunMetrics(
        prompt_version="v2",
        chunks=3,
        first_try_failures=0,
        retries=0,
        failed_parses=0,
        api_failures=0,
        cards_kept=8,
        cards_dropped=0,
    )

    log_metrics(m1, filepath=metrics_path)
    log_metrics(m2, filepath=metrics_path)

    with open(metrics_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    # Header + 2 data rows
    assert len(reader) == 3
    assert reader[0] == [
        "timestamp",
        "prompt_version",
        "chunks",
        "first_try_failures",
        "retries",
        "failed_parses",
        "api_failures",
        "cards_kept",
        "cards_dropped",
    ]
    assert reader[1][1] == "v1"
    assert reader[2][1] == "v2"
