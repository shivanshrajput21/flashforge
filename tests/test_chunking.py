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
        + ("Explanation word " * 160)
        + "\n\n## Topic Two\n"
        + ("Second explanation word " * 160)
    )
    chunks = chunk_text(notes, min_words=150, max_words=700, overlap_words=50)
    assert len(chunks) == 2
    assert chunks[0].startswith("# Topic One")
    assert chunks[1].startswith("## Topic Two")


def test_chunk_text_splits_large_section_with_overlap():
    words = [f"w{i}" for i in range(120)]
    text = " ".join(words)

    chunks = chunk_text(text, min_words=20, max_words=50, overlap_words=10)
    assert len(chunks) == 3
    assert chunks[0].split() == words[0:50]
    assert chunks[1].split() == words[40:90]
    assert chunks[2].split() == words[80:120]
    # Verify 10-word overlap between chunk 0 and chunk 1
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]


def test_chunk_text_empty_input():
    assert chunk_text("   \n\n  ") == []


def test_chunk_sample1_file_returns_one_or_two_chunks():
    with open("samples/sample1_microservices_short_headings.txt", "rb") as f:
        text = extract_text(f, filename="sample1_microservices_short_headings.txt")
    cleaned = clean_text(text)
    chunks = chunk_text(cleaned)
    assert 1 <= len(chunks) <= 2


def test_numbered_list_inside_section_stays_in_one_chunk():
    text = (
        "## Advantages of Monoliths\n"
        "1. Simplicity in early stages: Easier to develop, test, and deploy initially.\n"
        "2. Direct function calls: Inter-component communication occurs in-memory with near-zero latency.\n"
        "3. Unified transaction management: Relational databases handle ACID transactions across the whole domain easily.\n"
    )
    # The list items should not split into separate chunks
    chunks = chunk_text(text, min_words=10, max_words=700)
    assert len(chunks) == 1
    assert "1. Simplicity" in chunks[0]
    assert "3. Unified transaction" in chunks[0]


def test_no_chunk_is_just_a_heading():
    text = (
        "# Main Title\n\n"
        "## Section Subtitle\n\n"
        "### Minor Heading\n\n"
        "Here is the actual detailed body content that explains the concepts in depth. "
        "It provides enough context so the section has real substance and information."
    )
    chunks = chunk_text(text, min_words=10, max_words=700)
    for chunk in chunks:
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        # Verify chunk doesn't consist purely of heading markers
        non_headings = [line for line in lines if not line.startswith("#")]
        assert len(non_headings) > 0

