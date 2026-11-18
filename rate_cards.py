import argparse
import csv
import json
from pathlib import Path
import random
import sys


def sample_cards_for_rating(version: str, n: int, seed: int):
    """Sample n cards across results/cards_{version}_*.json and export to rating CSV."""
    results_dir = Path("results")
    card_files = sorted(results_dir.glob(f"cards_{version}_*.json"))

    if not card_files:
        print(f"Error: No card files found matching 'results/cards_{version}_*.json'.")
        print(f"Run compare_prompts.py with version '{version}' first.")
        sys.exit(1)

    cards_with_source: list[tuple[str, dict]] = []
    for file_path in card_files:
        sample_name = file_path.stem.replace(f"cards_{version}_", "")
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            for card in data:
                cards_with_source.append((sample_name, card))
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")

    if not cards_with_source:
        print(f"Error: No cards found in files for version '{version}'.")
        sys.exit(1)

    rng = random.Random(seed)
    # Shuffle and pick min(n, total available)
    rng.shuffle(cards_with_source)
    sampled = cards_with_source[: min(n, len(cards_with_source))]

    output_csv = results_dir / f"rating_{version}.csv"
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "question", "answer", "usable", "reason"])
        for sample_name, card in sampled:
            writer.writerow([sample_name, card.get("question", ""), card.get("answer", ""), "", ""])

    print(f"\n[Generated] Sampled {len(sampled)} cards across {len(card_files)} files (seed={seed}).")
    print(f"Saved to: {output_csv}")
    print("Open the CSV and fill the 'usable' column with 'yes' or 'no'.\n")


def score_rating_file(file_path: str):
    """Calculate and print the usable card rate from a completed rating CSV."""
    path = Path(file_path)
    if not path.is_file():
        print(f"Error: Rating file '{path}' does not exist.")
        sys.exit(1)

    total = 0
    usable_count = 0
    unrated = 0

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            val = (row.get("usable") or "").strip().lower()
            if val in ("yes", "y", "true", "1"):
                usable_count += 1
            elif val in ("no", "n", "false", "0"):
                pass
            else:
                unrated += 1

    if total == 0:
        print("Error: The rating file is empty.")
        return

    usable_rate = usable_count / total
    print("\n" + "=" * 50)
    print(f"RATING REPORT: {path.name}")
    print("=" * 50)
    print(f"Total Cards Evaluated: {total}")
    print(f"Usable Cards (Yes):    {usable_count}")
    print(f"Unusable Cards (No):   {total - usable_count - unrated}")
    if unrated > 0:
        print(f"Unrated (blank):       {unrated}")
    print(f"Usable-card Rate:      {usable_rate:.1%}")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Sample flashcards for manual human evaluation and compute usable rate."
    )
    parser.add_argument(
        "--version",
        default="v1",
        help="Prompt version to sample cards from (default: v1)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=20,
        help="Number of cards to sample (default: 20)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling (default: 42)",
    )
    parser.add_argument(
        "--score",
        type=str,
        default=None,
        help="Path to completed rating CSV to score (e.g. results/rating_v1.csv)",
    )
    args = parser.parse_args()

    if args.score:
        score_rating_file(args.score)
    else:
        sample_cards_for_rating(version=args.version, n=args.n, seed=args.seed)


if __name__ == "__main__":
    main()
