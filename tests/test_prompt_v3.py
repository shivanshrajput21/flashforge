from pathlib import Path
from generator import load_prompt, parse_and_validate
from app import get_available_prompt_versions


def test_v3_prompt_file_exists_and_loads():
    v3_path = Path("prompts") / "v3.txt"
    assert v3_path.is_file(), "prompts/v3.txt must exist"

    sample_notes = "Operating systems use virtual memory to isolate processes."
    prompt = load_prompt("v3", sample_notes)

    # Verify placeholder was replaced and required schema instructions exist
    assert sample_notes in prompt
    assert "{notes}" not in prompt
    assert '"question"' in prompt
    assert '"answer"' in prompt
    assert '"topic"' in prompt
    assert '"difficulty"' in prompt


def test_v3_prompt_discovered_by_app():
    versions = get_available_prompt_versions()
    assert "v3" in versions, "v3 must be discovered in available prompt versions"


def test_v3_schema_example_validates_cleanly():
    # Example snippet representing the structure requested by v3
    sample_v3_output = """
    [
      {
        "question": "Why does virtual memory prevent processes from corrupting each other's memory space?",
        "answer": "Each process operates in an isolated logical address space mapped to physical memory by the kernel.",
        "topic": "Operating Systems",
        "difficulty": "medium"
      }
    ]
    """
    cards, dropped = parse_and_validate(sample_v3_output)
    assert len(cards) == 1
    assert dropped == 0
    assert cards[0].difficulty.value == "medium"
    assert cards[0].topic == "Operating Systems"
