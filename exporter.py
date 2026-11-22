import csv
import io
import json
from pathlib import Path
import re

from models import Deck, Flashcard, RunMetrics

DECKS_DIR = Path("decks")
METRICS_FILE = Path("metrics.csv")


def sanitize_deck_name(name: str) -> str:
    """Sanitize deck name to be safe for filesystem storage (alphanumerics, dashes, underscores)."""
    cleaned = name.strip()
    # Replace slashes, backslashes, colons and other special characters with underscores
    sanitized = re.sub(r'[\/\\:*?"<>|]+', "_", cleaned)
    # Collapse multiple underscores/spaces
    sanitized = re.sub(r"\s+", "_", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized).strip("._ ")
    return sanitized if sanitized else "deck"


def export_csv(cards: list[Flashcard]) -> str:
    """Export flashcards to RFC-compliant CSV text with proper quoting and escaping."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["question", "answer", "topic", "difficulty"])
    for card in cards:
        writer.writerow([card.question, card.answer, card.topic, card.difficulty.value])
    return output.getvalue()


def export_anki(cards: list[Flashcard]) -> str:
    """Export flashcards to Anki tab-separated text with front, back, and tags."""
    lines = [
        "#separator:tab",
        "#html:false",
        "#tags column:3",
    ]
    for card in cards:
        # Replace newlines, carriage returns, and tabs in fields with single spaces
        front = re.sub(r"[\r\n\t]+", " ", card.question).strip()
        back = re.sub(r"[\r\n\t]+", " ", card.answer).strip()

        # Format tags: spaces replaced by underscores
        topic_tag = re.sub(r"\s+", "_", card.topic).strip("_")
        diff_tag = card.difficulty.value.strip()
        tags = f"{topic_tag} {diff_tag}".strip()

        lines.append(f"{front}\t{back}\t{tags}")

    return "\n".join(lines) + "\n"


def save_deck(deck_name: str, cards: list[Flashcard], prompt_version: str = "v1") -> Path:
    """Save flashcards as a JSON Deck file in the decks/ directory."""
    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = sanitize_deck_name(deck_name)
    deck_path = DECKS_DIR / f"{clean_name}.json"

    deck = Deck(
        name=clean_name,
        prompt_version=prompt_version,
        cards=cards,
    )
    deck_path.write_text(deck.model_dump_json(indent=2), encoding="utf-8")
    return deck_path


def load_deck(deck_name: str) -> Deck:
    """Load a Deck from decks/{deck_name}.json, raising clear errors if missing or invalid."""
    clean_name = sanitize_deck_name(deck_name)
    deck_path = DECKS_DIR / f"{clean_name}.json"

    if not deck_path.is_file():
        raise FileNotFoundError(f"Deck file '{deck_path}' does not exist.")

    try:
        raw_json = deck_path.read_text(encoding="utf-8")
        data = json.loads(raw_json)
        return Deck.model_validate(data)
    except Exception as e:
        raise ValueError(f"Failed to parse deck from '{deck_path}': {e}") from e


def list_decks() -> list[str]:
    """Return sorted list of saved deck names (without .json extension)."""
    if not DECKS_DIR.is_dir():
        return []
    return sorted(p.stem for p in DECKS_DIR.glob("*.json") if p.is_file())


def log_metrics(metrics: RunMetrics, filepath: Path = METRICS_FILE) -> None:
    """Append a RunMetrics record to metrics.csv, writing header only if file is missing."""
    file_exists = filepath.is_file() and filepath.stat().st_size > 0
    fieldnames = [
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

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(metrics.model_dump())
