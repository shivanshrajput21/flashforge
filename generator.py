import json
import os
from pathlib import Path
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import errors
from pydantic import ValidationError

from models import Flashcard, RunMetrics
from utils import chunk_text, clean_text, deduplicate

load_dotenv()


def get_client() -> genai.Client:
    """Initialize and return the Gemini API client using GEMINI_API_KEY from .env."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment or .env file.")
    return genai.Client(api_key=api_key)


def get_model_name() -> str:
    """Read configured Gemini model name from .env, defaulting to gemini-3.8-flash."""
    return os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()


def load_prompt(version: str, notes: str) -> str:
    """Read prompts/{version}.txt and substitute {notes} placeholder."""
    prompt_path = Path("prompts") / f"{version}.txt"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    template = prompt_path.read_text(encoding="utf-8")
    return template.replace("{notes}", notes)


def strip_code_fences(raw: str) -> str:
    """Strip markdown code block fences (e.g. ```json ... ```) and leading/trailing whitespace."""
    text = raw.strip()
    # Match ```optional_lang\n ... \n```
    fence_pattern = re.compile(r"^```(?:[a-zA-Z0-9_\-]+)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence_pattern.match(text)
    if match:
        return match.group(1).strip()
    return text


def parse_and_validate(raw_text: str) -> tuple[list[Flashcard], int]:
    """Parse JSON and validate each item with Flashcard schema.

    Returns (valid_cards, dropped_count).
    Raises json.JSONDecodeError if JSON syntax is malformed.
    """
    cleaned_json = strip_code_fences(raw_text)
    data = json.loads(cleaned_json)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of flashcard objects, got {type(data).__name__}.")

    valid_cards: list[Flashcard] = []
    dropped_count = 0

    for item in data:
        if not isinstance(item, dict):
            dropped_count += 1
            continue
        try:
            card = Flashcard.model_validate(item)
            valid_cards.append(card)
        except ValidationError:
            dropped_count += 1

    return valid_cards, dropped_count


def _extract_retry_delay_seconds(error_message: str, default_delay: float) -> float:
    """Parse 'retry in Ns' or 'retry after N seconds' if provided by Gemini error response."""
    match = re.search(r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*s?", error_message, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)) + 0.5
        except ValueError:
            pass
    return default_delay


def _call_gemini(client: genai.Client, model: str, prompt: str) -> str:
    """Execute single LLM call and return text response, with backoff on transient errors."""
    import time
    max_api_attempts = 4
    delay = 2.0

    for attempt in range(1, max_api_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return response.text or ""
        except errors.APIError as e:
            # 503 Service Unavailable / high demand or 429 Rate Limit
            msg = str(e).lower()
            if (e.code in (429, 503) or "demand" in msg or "quota" in msg) and attempt < max_api_attempts:
                wait_time = _extract_retry_delay_seconds(str(e), delay)
                time.sleep(wait_time)
                delay *= 2
                continue
            raise RuntimeError(f"Gemini API Error ({e.code}): {e.message}") from e
        except Exception as e:
            if attempt < max_api_attempts:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"Gemini Request Failed: {e}") from e


def generate_cards_for_chunk(
    client: genai.Client,
    model: str,
    chunk: str,
    prompt_version: str,
    max_retries: int = 2,
) -> tuple[list[Flashcard], int, int, int, int]:
    """Process a single text chunk with Gemini.

    Returns (valid_cards, retries_used, failed_parses, dropped_count, first_try_failed).
    Retries up to max_retries on JSON decode or schema structure errors.
    """
    retries = 0
    failed_parses = 0
    first_try_failed = 0
    prompt = load_prompt(prompt_version, chunk)

    while True:
        try:
            raw_response = _call_gemini(client, model, prompt)
            cards, dropped = parse_and_validate(raw_response)
            return cards, retries, failed_parses, dropped, first_try_failed
        except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
            failed_parses += 1
            if retries == 0:
                first_try_failed = 1
            if retries < max_retries:
                retries += 1
                # Nudge the prompt on retry to reinforce JSON formatting
                prompt = (
                    f"{load_prompt(prompt_version, chunk)}\n\n"
                    "CRITICAL: Your previous response was invalid. Output ONLY a valid JSON list "
                    "of objects with keys 'question', 'answer', 'topic', 'difficulty'."
                )
            else:
                # Retries exhausted; return empty list for this chunk
                return [], retries, failed_parses, 0, first_try_failed


def generate_cards(
    text: str,
    prompt_version: str = "v1",
    similarity_threshold: float = 0.85,
    chunk_delay_seconds: float = 0.5,
) -> tuple[list[Flashcard], RunMetrics]:
    """Full generation pipeline: clean, chunk, generate per chunk, merge, and deduplicate."""
    import time

    cleaned = clean_text(text)
    chunks = chunk_text(cleaned)

    if not chunks:
        empty_metrics = RunMetrics(
            prompt_version=prompt_version,
            chunks=0,
            first_try_failures=0,
            retries=0,
            failed_parses=0,
            cards_kept=0,
            cards_dropped=0,
        )
        return [], empty_metrics

    client = get_client()
    model = get_model_name()

    all_raw_cards: list[Flashcard] = []
    total_retries = 0
    total_failed_parses = 0
    total_dropped = 0
    total_first_try_failures = 0

    for idx, chunk in enumerate(chunks):
        if idx > 0 and chunk_delay_seconds > 0:
            time.sleep(chunk_delay_seconds)

        chunk_cards, retries, failed_parses, dropped, first_try_failed = generate_cards_for_chunk(
            client=client,
            model=model,
            chunk=chunk,
            prompt_version=prompt_version,
        )
        all_raw_cards.extend(chunk_cards)
        total_retries += retries
        total_failed_parses += failed_parses
        total_dropped += dropped
        total_first_try_failures += first_try_failed

    # Deduplicate merged cards across chunks
    kept_cards = deduplicate(all_raw_cards, threshold=similarity_threshold)
    duplicate_drops = len(all_raw_cards) - len(kept_cards)
    total_dropped += duplicate_drops

    metrics = RunMetrics(
        prompt_version=prompt_version,
        chunks=len(chunks),
        first_try_failures=total_first_try_failures,
        retries=total_retries,
        failed_parses=total_failed_parses,
        cards_kept=len(kept_cards),
        cards_dropped=total_dropped,
    )

    return kept_cards, metrics

