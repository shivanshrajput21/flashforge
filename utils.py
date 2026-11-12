from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import BinaryIO

from pypdf import PdfReader

from models import Flashcard

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?\s*$",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|\d+(?:\.\d+)*\.?\s+[A-Z].+)$",
    re.MULTILINE,
)


def extract_text(source: str | BinaryIO, filename: str | None = None) -> str:
    """Extract raw text from pasted strings, .txt files, or .pdf files."""
    if isinstance(source, str):
        return source

    name = filename or getattr(source, "name", "")
    ext = Path(name).suffix.lower()

    if ext == ".pdf":
        reader = PdfReader(source)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    raw = source.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def clean_text(text: str) -> str:
    """Normalize whitespace, strip standalone page numbers, and drop repeated headers/footers."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    # Identify short lines that repeat 3+ times (typical PDF headers/footers).
    short_lines = [
        line.strip()
        for line in lines
        if line.strip() and len(line.strip()) <= 80
    ]
    counts = Counter(short_lines)
    repeated = {line for line, count in counts.items() if count >= 3}

    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in repeated:
            continue
        if _PAGE_NUMBER_RE.match(stripped):
            continue
        # Collapse runs of spaces/tabs inside a line.
        cleaned_lines.append(re.sub(r"[ \t]+", " ", stripped))

    joined = "\n".join(cleaned_lines)
    # Collapse 3+ consecutive newlines down to a single blank line.
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _split_by_headings(text: str) -> list[str]:
    """Split text into sections starting at markdown or numbered headings."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [text] if text.strip() else []

    sections: list[str] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(preamble)

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)

    return sections


def _split_words_with_overlap(
    text: str,
    max_words: int,
    overlap_words: int,
) -> list[str]:
    """Split text into word windows of at most max_words with overlap_words overlap."""
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()] if words else []

    step = max(1, max_words - overlap_words)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        end = start + max_words
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
    return chunks


def chunk_text(
    text: str,
    max_words: int = 700,
    overlap_words: int = 50,
) -> list[str]:
    """Split text by headings first, then sub-split oversized sections with overlap."""
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    for section in _split_by_headings(text):
        if len(section.split()) <= max_words:
            chunks.append(section)
        else:
            chunks.extend(_split_words_with_overlap(section, max_words, overlap_words))
    return chunks


def _normalize_question(question: str) -> str:
    """Lowercase and collapse whitespace for duplicate comparison."""
    return " ".join(question.lower().split())


def deduplicate(
    cards: list[Flashcard],
    threshold: float = 0.85,
) -> list[Flashcard]:
    """Remove exact and near-duplicate flashcards based on question similarity."""
    kept: list[Flashcard] = []
    kept_questions: list[str] = []
    seen_exact: set[str] = set()

    for card in cards:
        norm_q = _normalize_question(card.question)
        if norm_q in seen_exact:
            continue

        is_near_duplicate = any(
            SequenceMatcher(None, norm_q, existing_q).ratio() >= threshold
            for existing_q in kept_questions
        )
        if is_near_duplicate:
            continue

        seen_exact.add(norm_q)
        kept_questions.append(norm_q)
        kept.append(card)

    return kept

