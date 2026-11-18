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


# Default delay in seconds between chunk calls to stay well under 15 RPM
CHUNK_DELAY_SECONDS = 4.0


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
    """Read prompts/{version}.txt and substitute {notes} placeholder.

    Uses .replace() so curly braces inside prompt examples (e.g. JSON schemas)
    are preserved without causing str.format KeyError issues.
    """
    prompt_path = Path("prompts") / f"{version}.txt"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    template = prompt_path.read_text(encoding="utf-8")
    if "{notes}" not in template:
        raise ValueError(f"Prompt template '{prompt_path}' is missing required '{{notes}}' placeholder.")

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


def _call_gemini(
    client: genai.Client,
    model: str,
    prompt: str,
    backoff_delays: tuple[float, ...] = (5.0, 15.0, 30.0, 60.0, 90.0),
) -> str:
    """Execute single LLM call with backoff on 503/429/demand errors."""
    import time

    total_attempts = len(backoff_delays) + 1
    for attempt_idx in range(total_attempts):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return response.text or ""
        except errors.APIError as e:
            msg = str(e).lower()
            is_transient = e.code in (429, 503) or "demand" in msg or "quota" in msg or "unavailable" in msg
            if is_transient and attempt_idx < len(backoff_delays):
                delay = _extract_retry_delay_seconds(str(e), backoff_delays[attempt_idx])
                print(f"Server busy ({e.code or 'high demand'}), waiting {delay:.1f}s...")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Gemini API Error ({e.code}): {e.message}") from e
        except Exception as e:
            msg = str(e).lower()
            is_transient = "503" in msg or "429" in msg or "demand" in msg or "unavailable" in msg
            if is_transient and attempt_idx < len(backoff_delays):
                delay = backoff_delays[attempt_idx]
                print(f"Server busy, waiting {delay:.1f}s...")
                time.sleep(delay)
                continue
            raise RuntimeError(f"Gemini Request Failed: {e}") from e

    raise RuntimeError("Gemini API call failed after all retry attempts.")


def generate_cards_for_chunk(
    client: genai.Client,
    model: str,
    chunk: str,
    prompt_version: str,
    max_retries: int = 2,
    raw_output_prefix: str | None = None,
    chunk_index: int = 1,
) -> tuple[list[Flashcard], int, int, int, int, int]:
    """Process a single text chunk with Gemini.

    Returns (valid_cards, retries_used, failed_parses, dropped_count, first_try_failed, api_failed).
    Retries up to max_retries on JSON decode or schema structure errors.
    If Gemini API fails after all backoff retries, returns api_failed=1 and continues.
    """
    retries = 0
    failed_parses = 0
    first_try_failed = 0
    api_failed = 0
    prompt = load_prompt(prompt_version, chunk)

    while True:
        attempt_number = retries + 1
        raw_response = ""
        try:
            raw_response = _call_gemini(client, model, prompt)
        except Exception as api_err:
            print(f"Warning: Chunk {chunk_index} API call failed: {api_err}")
            api_failed = 1
            # Return empty cards for this chunk without breaking the entire run
            return [], retries, failed_parses, 0, first_try_failed, api_failed

        if raw_output_prefix:
            out_dir = Path("raw_outputs")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{raw_output_prefix}_chunk{chunk_index}_attempt{attempt_number}.txt"
            out_file.write_text(raw_response, encoding="utf-8")

        try:
            cards, dropped = parse_and_validate(raw_response)
            return cards, retries, failed_parses, dropped, first_try_failed, api_failed
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
                return [], retries, failed_parses, 0, first_try_failed, api_failed


def generate_cards(
    text: str,
    prompt_version: str = "v1",
    similarity_threshold: float = 0.85,
    chunk_delay_seconds: float = CHUNK_DELAY_SECONDS,
    raw_output_prefix: str | None = None,
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
    total_api_failures = 0

    for idx, chunk in enumerate(chunks, start=1):
        if idx > 1 and chunk_delay_seconds > 0:
            time.sleep(chunk_delay_seconds)

        chunk_cards, retries, failed_parses, dropped, first_try_failed, api_failed = (
            generate_cards_for_chunk(
                client=client,
                model=model,
                chunk=chunk,
                prompt_version=prompt_version,
                raw_output_prefix=raw_output_prefix,
                chunk_index=idx,
            )
        )
        all_raw_cards.extend(chunk_cards)
        total_retries += retries
        total_failed_parses += failed_parses
        total_dropped += dropped
        total_first_try_failures += first_try_failed
        total_api_failures += api_failed

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
        api_failures=total_api_failures,
        cards_kept=len(kept_cards),
        cards_dropped=total_dropped,
    )

    return kept_cards, metrics

