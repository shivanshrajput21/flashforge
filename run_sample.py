import argparse
import sys
from pathlib import Path

from generator import generate_cards
from utils import extract_text


def main():
    parser = argparse.ArgumentParser(
        description="Run FlashForge card generation on a sample document."
    )
    parser.add_argument(
        "--file",
        "-f",
        default="samples/sample1_microservices_short_headings.txt",
        help="Path to sample file (default: samples/sample1_microservices_short_headings.txt)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        default="v1",
        help="Prompt version name in prompts/ (default: v1)",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: Sample file '{file_path}' does not exist.")
        sys.exit(1)

    print(f"=== Reading {file_path} ===")
    with open(file_path, "rb") as f:
        raw_text = extract_text(f, filename=file_path.name)

    print(f"Raw character length: {len(raw_text)}")
    print(f"Using prompt version: {args.prompt}")
    print("Calling Gemini API...")

    try:
        cards, metrics = generate_cards(raw_text, prompt_version=args.prompt)
    except Exception as e:
        print(f"\nExecution failed: {e}")
        sys.exit(1)

    print("\n=== Generation Metrics ===")
    print(f"Timestamp:           {metrics.timestamp}")
    print(f"Prompt Version:      {metrics.prompt_version}")
    print(f"Total Chunks:        {metrics.chunks}")
    print(f"First-try Failures:  {metrics.first_try_failures}")
    print(f"Retries Used:        {metrics.retries}")
    print(f"Failed Parses:       {metrics.failed_parses}")
    print(f"Cards Kept:          {metrics.cards_kept}")
    print(f"Cards Dropped:       {metrics.cards_dropped}")

    print(f"\n=== Generated Cards ({len(cards)}) ===")
    for idx, card in enumerate(cards, start=1):
        print(f"\n[{idx}] Topic: {card.topic} | Difficulty: {card.difficulty.value}")
        print(f"Q: {card.question}")
        print(f"A: {card.answer}")


if __name__ == "__main__":
    main()

