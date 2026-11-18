import argparse
import csv
import json
from pathlib import Path
import sys

from generator import generate_cards
from utils import extract_text


def run_comparison(versions: list[str], sample_paths: list[Path], resume: bool = False):
    """Run generate_cards across multiple prompt versions and samples with instant logging."""
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    comparison_csv_path = results_dir / "comparison.csv"

    # Identify already completed (version, sample) pairs if resume is set
    completed_pairs = set()
    if resume and comparison_csv_path.is_file():
        with open(comparison_csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed_pairs.add((row.get("version"), row.get("sample")))

    # Verify which versions actually exist
    available_versions = []
    for v in versions:
        prompt_file = Path("prompts") / f"{v}.txt"
        if prompt_file.is_file():
            available_versions.append(v)
        else:
            print(f"[Notice] Skipping '{v}': prompt file '{prompt_file}' does not exist.")

    if not available_versions:
        print("Error: None of the specified prompt versions exist in prompts/.")
        sys.exit(1)

    print(f"\nRunning comparison across versions: {available_versions}")
    print(f"Samples ({len(sample_paths)}): {[p.name for p in sample_paths]}")
    if resume:
        print(f"Resume active: {len(completed_pairs)} pairs already logged in {comparison_csv_path.name}")

    # Initialize CSV header if file doesn't exist
    fieldnames = [
        "version",
        "sample",
        "chunks",
        "first_try_failures",
        "retries",
        "api_failures",
        "cards_kept",
        "cards_dropped",
    ]
    if not comparison_csv_path.is_file():
        with open(comparison_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

    version_stats = {
        v: {
            "total_chunks": 0,
            "first_try_failures": 0,
            "retries": 0,
            "api_failures": 0,
            "cards_kept": 0,
            "cards_dropped": 0,
            "total_words": 0,
        }
        for v in available_versions
    }

    # Populate stats from existing rows if resuming
    if comparison_csv_path.is_file():
        with open(comparison_csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                v = row.get("version")
                if v in version_stats:
                    v_stat = version_stats[v]
                    v_stat["total_chunks"] += int(row.get("chunks", 0))
                    v_stat["first_try_failures"] += int(row.get("first_try_failures", 0))
                    v_stat["retries"] += int(row.get("retries", 0))
                    v_stat["api_failures"] += int(row.get("api_failures", 0))
                    v_stat["cards_kept"] += int(row.get("cards_kept", 0))
                    v_stat["cards_dropped"] += int(row.get("cards_dropped", 0))

    for version in available_versions:
        print(f"\n==================== Version: {version} ====================")
        for sample_path in sample_paths:
            sample_name = sample_path.name
            if (version, sample_name) in completed_pairs:
                print(f"[Skip] {version} on {sample_name} already completed.")
                continue

            print(f"\n--> Running on: {sample_name}")

            try:
                with open(sample_path, "rb") as f:
                    raw_text = extract_text(f, filename=sample_name)

                cards, metrics = generate_cards(
                    raw_text,
                    prompt_version=version,
                    raw_output_prefix=f"{sample_path.stem}_{version}",
                )

                # Save generated cards to JSON
                cards_out = results_dir / f"cards_{version}_{sample_path.stem}.json"
                cards_data = [card.model_dump() for card in cards]
                cards_out.write_text(json.dumps(cards_data, indent=2), encoding="utf-8")

                row = {
                    "version": version,
                    "sample": sample_name,
                    "chunks": metrics.chunks,
                    "first_try_failures": metrics.first_try_failures,
                    "retries": metrics.retries,
                    "api_failures": metrics.api_failures,
                    "cards_kept": metrics.cards_kept,
                    "cards_dropped": metrics.cards_dropped,
                }

                # Immediately append to comparison.csv
                with open(comparison_csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(row)

                # Update live stats
                v_stat = version_stats[version]
                v_stat["total_chunks"] += metrics.chunks
                v_stat["first_try_failures"] += metrics.first_try_failures
                v_stat["retries"] += metrics.retries
                v_stat["api_failures"] += metrics.api_failures
                v_stat["cards_kept"] += metrics.cards_kept
                v_stat["cards_dropped"] += metrics.cards_dropped
                for card in cards:
                    v_stat["total_words"] += len(card.answer.split())

                print(
                    f"    Chunks: {metrics.chunks} | First-try fails: {metrics.first_try_failures} | "
                    f"Retries: {metrics.retries} | API fails: {metrics.api_failures} | "
                    f"Kept: {metrics.cards_kept} | Dropped: {metrics.cards_dropped}"
                )

            except Exception as e:
                print(f"FAILED: {e}")
                # Log failed attempt row so state isn't lost
                failed_row = {
                    "version": version,
                    "sample": sample_name,
                    "chunks": 0,
                    "first_try_failures": 0,
                    "retries": 0,
                    "api_failures": 1,
                    "cards_kept": 0,
                    "cards_dropped": 0,
                }
                with open(comparison_csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(failed_row)

    print(f"\n[Saved] Detailed results written to {comparison_csv_path}")

    # Print Summary Table
    print("\n" + "=" * 80)
    print("SUMMARY BY PROMPT VERSION")
    print("=" * 80)
    header = (
        f"{'Version':<10} | {'Chunks':<8} | {'1st-Fail Rate':<14} | "
        f"{'API Fails':<10} | {'Kept':<8} | {'Dropped':<8} | {'Drop Rate':<10} | {'Avg Ans Words':<14}"
    )
    print(header)
    print("-" * len(header))

    for v in available_versions:
        st = version_stats[v]
        chunks = st["total_chunks"]
        first_fail_rate = (st["first_try_failures"] / chunks) if chunks > 0 else 0.0
        total_gen = st["cards_kept"] + st["cards_dropped"]
        drop_rate = (st["cards_dropped"] / total_gen) if total_gen > 0 else 0.0
        avg_words = (st["total_words"] / st["cards_kept"]) if st["cards_kept"] > 0 else 0.0

        print(
            f"{v:<10} | {chunks:<8} | {first_fail_rate:>13.1%} | "
            f"{st['api_failures']:<10} | {st['cards_kept']:<8} | {st['cards_dropped']:<8} | {drop_rate:>9.1%} | {avg_words:>13.1f}"
        )
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Compare flashcard generation across prompt versions."
    )
    parser.add_argument(
        "--versions",
        nargs="+",
        default=["v1"],
        help="Prompt versions to evaluate (e.g. --versions v1 v2 v3)",
    )
    parser.add_argument(
        "--samples",
        nargs="*",
        default=None,
        help="Specific sample file names or paths (default: all files in samples/)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip (version, sample) pairs already logged in results/comparison.csv",
    )
    args = parser.parse_args()

    if args.samples:
        sample_paths = [Path(s) if Path(s).exists() else Path("samples") / s for s in args.samples]
    else:
        sample_paths = sorted(Path("samples").iterdir())

    valid_samples = [p for p in sample_paths if p.is_file()]
    if not valid_samples:
        print("Error: No sample files found.")
        sys.exit(1)

    run_comparison(versions=args.versions, sample_paths=valid_samples, resume=args.resume)


if __name__ == "__main__":
    main()
