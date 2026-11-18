import pytest
from pathlib import Path
from generator import load_prompt


def test_load_prompt_replaces_notes_placeholder(tmp_path, monkeypatch):
    test_prompts_dir = tmp_path / "prompts"
    test_prompts_dir.mkdir()
    (test_prompts_dir / "test_v.txt").write_text("Hello {notes} world!", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = load_prompt("test_v", "study notes here")
    assert result == "Hello study notes here world!"


def test_load_prompt_preserves_json_braces(tmp_path, monkeypatch):
    test_prompts_dir = tmp_path / "prompts"
    test_prompts_dir.mkdir()
    template = 'Return schema: [{"question": "{notes}", "tags": {"key": 1}}]'
    (test_prompts_dir / "schema_v.txt").write_text(template, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = load_prompt("schema_v", "my sample note")
    assert result == 'Return schema: [{"question": "my sample note", "tags": {"key": 1}}]'


def test_load_prompt_missing_placeholder_raises_value_error(tmp_path, monkeypatch):
    test_prompts_dir = tmp_path / "prompts"
    test_prompts_dir.mkdir()
    (test_prompts_dir / "bad_v.txt").write_text("No placeholder in this prompt template.", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="missing required '{notes}' placeholder"):
        load_prompt("bad_v", "test notes")


def test_load_prompt_nonexistent_file_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_version", "test notes")
