from unittest.mock import MagicMock
from google.genai import errors

from generator import generate_cards_for_chunk
from models import Difficulty


def test_chunk_recovers_after_transient_503(monkeypatch):
    """Simulate a 503 high demand error followed by a successful JSON response."""
    # Fast-forward time.sleep during tests
    monkeypatch.setattr("time.sleep", lambda s: None)

    mock_client = MagicMock()
    first_attempt = True

    def side_effect(model, contents):
        nonlocal first_attempt
        if first_attempt:
            first_attempt = False
            # Simulate 503 high demand error
            raise errors.APIError(503, "The model is overloaded. High demand.")

        mock_resp = MagicMock()
        mock_resp.text = (
            '[{"question": "What is virtual memory?", '
            '"answer": "Memory management that abstracts physical storage.", '
            '"topic": "OS", "difficulty": "medium"}]'
        )
        return mock_resp

    mock_client.models.generate_content.side_effect = side_effect

    cards, retries, failed_parses, dropped, first_try_failed, api_failed = generate_cards_for_chunk(
        client=mock_client,
        model="test-model",
        chunk="Sample chunk text about virtual memory",
        prompt_version="v1",
    )

    # Chunk should succeed and return the card
    assert len(cards) == 1
    assert cards[0].question == "What is virtual memory?"
    assert cards[0].difficulty == Difficulty.medium

    # Transient 503 wait does NOT count as prompt retry or parse failure
    assert retries == 0
    assert failed_parses == 0
    assert first_try_failed == 0
    assert api_failed == 0
