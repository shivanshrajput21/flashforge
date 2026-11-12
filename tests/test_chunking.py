import io
from utils import clean_text, chunk_text, extract_text


def test_extract_text_pasted_and_txt():
    assert extract_text("Hello notes") == "Hello notes"

    txt_stream = io.BytesIO(b"Line one\nLine two")
    assert extract_text(txt_stream, filename="notes.txt") == "Line one\nLine two"


def test_clean_text_strips_whitespace_page_numbers_and_headers():
    raw = (
        "CS101 Lecture Notes\n"
        "Page 1\n"
        "  First   paragraph   here.\n\n\n\n"
        "CS101 Lecture Notes\n"
        "2 / 10\n"
        "Second paragraph here.\n"
        "CS101 Lecture Notes\n"
        "3\n"
    )
    cleaned = clean_text(raw)
    assert "CS101 Lecture Notes" not in cleaned
    assert "Page 1" not in cleaned
    assert "2 / 10" not in cleaned
    assert cleaned == "First paragraph here.\n\nSecond paragraph here."


def test_chunk_text_splits_by_headings_when_small():
    notes = (
        "# Topic One\n"
        "Short explanation of topic one.\n\n"
        "## Topic Two\n"
        "Short explanation of topic two."
    )
    chunks = chunk_text(notes, max_words=700, overlap_words=50)
    assert len(chunks) == 2
    assert chunks[0].startswith("# Topic One")
    assert chunks[1].startswith("## Topic Two")


def test_chunk_text_splits_large_section_with_overlap():
    words = [f"w{i}" for i in range(120)]
    text = " ".join(words)

    chunks = chunk_text(text, max_words=50, overlap_words=10)
    assert len(chunks) == 3
    assert chunks[0].split() == words[0:50]
    assert chunks[1].split() == words[40:90]
    assert chunks[2].split() == words[80:120]
    # Verify 10-word overlap between chunk 0 and chunk 1
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]


def test_chunk_text_empty_input():
    assert chunk_text("   \n\n  ") == []

