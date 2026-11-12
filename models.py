from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class Difficulty(str, Enum):
    """Allowed difficulty levels for a flashcard."""

    easy = "easy"
    medium = "medium"
    hard = "hard"


class RevisionStatus(str, Enum):
    """Study progress status for a flashcard in revision mode."""

    unreviewed = "unreviewed"
    known = "known"
    needs_review = "needs_review"


class Flashcard(BaseModel):
    """Single Q&A flashcard validated against FlashForge rules."""

    question: str
    answer: str
    topic: str = "General"
    difficulty: Difficulty
    status: RevisionStatus = RevisionStatus.unreviewed

    @field_validator("question", "answer")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        """Strip whitespace and reject empty questions or answers."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty.")
        return cleaned

    @field_validator("answer")
    @classmethod
    def answer_max_40_words(cls, value: str) -> str:
        """Enforce concise answers (40 words or fewer)."""
        word_count = len(value.split())
        if word_count > 40:
            raise ValueError(f"Answer too long ({word_count} words; max is 40).")
        return value

    @field_validator("topic", mode="before")
    @classmethod
    def normalize_topic(cls, value: object) -> str:
        """Trim topic whitespace and fall back to 'General' if blank or missing."""
        if not isinstance(value, str):
            return "General"
        cleaned = value.strip()
        return cleaned if cleaned else "General"

    @field_validator("difficulty", mode="before")
    @classmethod
    def normalize_difficulty(cls, value: object) -> object:
        """Accept case-insensitive difficulty strings (e.g. 'Easy' -> 'easy')."""
        if isinstance(value, str):
            return value.strip().lower()
        return value


class Deck(BaseModel):
    """A saved collection of flashcards for local JSON persistence."""

    name: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    prompt_version: str = "v1"
    cards: list[Flashcard] = Field(default_factory=list)


class RunMetrics(BaseModel):
    """Per-run generation metrics logged to metrics.csv."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    prompt_version: str
    chunks: int
    retries: int
    failed_parses: int
    cards_kept: int
    cards_dropped: int

