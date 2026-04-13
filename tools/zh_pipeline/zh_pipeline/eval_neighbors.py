from __future__ import annotations

import argparse
import json
from pathlib import Path

from .constants import DEFAULT_DATA_DIR, DEFAULT_SIMILARITY_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect nearest neighbors for sample Chinese words."
    )
    parser.add_argument(
        "words",
        nargs="+",
        help="One or more query words to inspect.",
    )
    parser.add_argument(
        "--input-path",
        default=str(DEFAULT_DATA_DIR / DEFAULT_SIMILARITY_NAME),
        help="Path to the similarity JSONL file.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="How many nearest neighbors to print per query word.",
    )
    parser.add_argument(
        "--contains",
        action="store_true",
        help="If an exact row is missing, also print words containing the query substring.",
    )
    return parser


def load_rows(input_path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with input_path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[row["word"]] = row
    return rows


def print_neighbors(word: str, row: dict, top_k: int) -> None:
    print(f"\n{word}")
    print(f"count={row['count']} doc_frequency={row['doc_frequency']}")
    neighbors = row.get("neighbors", [])[:top_k]
    if not neighbors:
        print("  (no neighbors)")
        return

    for neighbor in neighbors:
        print(
            f"  {neighbor['rank']:>2}. {neighbor['word']}  score={neighbor['score']:.6f}"
        )


def print_contains_matches(word: str, rows: dict[str, dict], limit: int = 12) -> None:
    matches = sorted(candidate for candidate in rows if word in candidate)[:limit]
    if not matches:
        print("  no substring matches")
        return
    print("  substring matches:")
    for match in matches:
        print(f"    - {match}")


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input_path).resolve()
    rows = load_rows(input_path)

    print(f"Loaded {len(rows)} similarity rows from {input_path}")
    for word in args.words:
        row = rows.get(word)
        if row is None:
            print(f"\n{word}")
            print("  exact row not found")
            if args.contains:
                print_contains_matches(word, rows)
            continue
        print_neighbors(word, row, args.top_k)


if __name__ == "__main__":
    main()
