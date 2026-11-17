from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import BinaryIO

from pypdf import PdfReader

from models import Flashcard


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


_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:page\s*)?\d+(?:\s*(?:/|of)\s*\d+)?\s*$",
    re.IGNORECASE,
)
# Match markdown headers (# through ###) OR short title lines (e.g. "1. Introduction", "Chapter 3")
# with no colons, no punctuation-terminated body sentences, and length <= 60 chars.
_MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,3}\s+\S.*$")
_NUMBERED_TITLE_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|chapter\s+\d+)\s+[^:\n]{2,50}$", re.IGNORECASE)


def _is_heading_line(line: str) -> bool:
    """Identify if a line is a true heading vs a numbered list item or body sentence."""
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return False
    if _MARKDOWN_HEADING_RE.match(stripped):
        return True
    if _NUMBERED_TITLE_RE.match(stripped):
        # Exclude list items that contain colon definitions or trailing sentence periods
        if ":" in stripped or stripped.endswith("."):
            return False
        return True
    return False


def _split_by_headings(text: str) -> list[str]:
    """Split text into sections starting at markdown (#..###) or short title lines."""
    lines = text.split("\n")
    sections: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        if _is_heading_line(line):
            if current_lines:
                sec = "\n".join(current_lines).strip()
                if sec:
                    sections.append(sec)
                current_lines = []
        current_lines.append(line)

    if current_lines:
        sec = "\n".join(current_lines).strip()
        if sec:
            sections.append(sec)

    return sections


def _merge_small_sections(
    sections: list[str],
    min_words: int = 150,
    max_words: int = 700,
) -> list[str]:
    """Merge small consecutive sections so each chunk has at least min_words (up to max_words).

    A heading never remains isolated because it is joined with subsequent sections.
    """
    if not sections:
        return []

    merged: list[str] = []
    buffer: list[str] = []
    buffer_words = 0

    for sec in sections:
        sec_words = len(sec.split())
        if not buffer:
            buffer.append(sec)
            buffer_words = sec_words
            continue

        if buffer_words < min_words and (buffer_words + sec_words) <= max_words:
            buffer.append(sec)
            buffer_words += sec_words
        elif buffer_words < min_words and (buffer_words + sec_words) > max_words:
            # Buffer must be flushed even if small if next section pushes past max_words
            merged.append("\n\n".join(buffer).strip())
            buffer = [sec]
            buffer_words = sec_words
        else:
            # Buffer has met min_words
            merged.append("\n\n".join(buffer).strip())
            buffer = [sec]
            buffer_words = sec_words

    if buffer:
        final_sec = "\n\n".join(buffer).strip()
        if merged and len(final_sec.split()) < min_words:
            # If the trailing remainder is tiny, fold it into the previous chunk if it fits
            prev_words = len(merged[-1].split())
            if prev_words + len(final_sec.split()) <= max_words:
                merged[-1] = f"{merged[-1]}\n\n{final_sec}".strip()
            else:
                merged.append(final_sec)
        else:
            merged.append(final_sec)

    return merged


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
    min_words: int = 150,
    max_words: int = 700,
    overlap_words: int = 50,
) -> list[str]:
    """Split text by headings, merge small sections to >= min_words, and split oversized sections."""
    if not text or not text.strip():
        return []

    raw_sections = _split_by_headings(text)
    merged_sections = _merge_small_sections(raw_sections, min_words=min_words, max_words=max_words)

    final_chunks: list[str] = []
    for section in merged_sections:
        words_count = len(section.split())
        if words_count <= max_words:
            final_chunks.append(section)
        else:
            final_chunks.extend(
                _split_words_with_overlap(section, max_words=max_words, overlap_words=overlap_words)
            )

    return final_chunks


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

