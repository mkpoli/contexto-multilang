"""Re-filter the playable_ids list in a generated model's metadata.json.

Tokenizes each playable word with SudachiPy + UniDic-derived dictionary and
removes entries whose dominant POS is in --exclude-pos. The default excludes
verbs (動詞), which our SVD-on-cooccurrence embeddings handle poorly because
lemmatization collapses many distinct syntactic roles into one row.

Variants and embeddings are not touched, so excluded words remain *guessable*
— players can type them and get a meaningful rank — they're just never chosen
as the target.

Usage:
    uv run game-vocab-refilter-playable --input-dir src/lib/generated/ja-game
    uv run game-vocab-refilter-playable --input-dir .snapshots/ja-game-old --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from sudachipy import dictionary, tokenizer

from game_vocab_tools.common import display_word, load_json


DEFAULT_EXCLUDE = ("動詞", "副詞")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Re-filter playable_ids in metadata.json based on POS, "
            "so verbs (and other POS) can be kept guessable but excluded "
            "from being puzzle answers."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  game-vocab-refilter-playable --input-dir src/lib/generated/ja-game\n"
            "  game-vocab-refilter-playable --input-dir .snapshots/ja-game-old \\\n"
            "      --exclude-pos 動詞,副詞,形容詞 --dry-run"
        ),
    )
    parser.add_argument(
        "--input-dir", required=True, help="Path to a generated model directory."
    )
    parser.add_argument(
        "--exclude-pos",
        default=",".join(DEFAULT_EXCLUDE),
        help=(
            "Comma-separated top-level POS labels to exclude from playable_ids "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the breakdown without rewriting metadata.json.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing metadata.json.bak (which is created by default).",
    )
    parser.add_argument(
        "--show-samples",
        type=int,
        default=8,
        help="Number of excluded sample words to print per POS (default: %(default)s).",
    )
    return parser


def make_tokenizer():
    tok = dictionary.Dictionary().create()
    return tok, tokenizer.Tokenizer.SplitMode.C


def dominant_pos(word: str, tok, mode) -> str:
    """Tokenize `word` and return the high-level POS of its dominant morpheme.

    For a clean single-morpheme word the answer is unambiguous. For compound
    inputs we return the POS of the longest morpheme — this matches how the
    word would behave as a unit in the game.
    """
    morphemes = list(tok.tokenize(word, mode))
    if not morphemes:
        return ""
    head = max(morphemes, key=lambda m: len(m.surface()))
    return head.part_of_speech()[0]


def main() -> None:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir).resolve()
    metadata_path = input_dir / "metadata.json"
    vocab_path = input_dir / "vocab.json"

    metadata = load_json(metadata_path)
    vocab = load_json(vocab_path)
    excluded_pos = {p.strip() for p in args.exclude_pos.split(",") if p.strip()}

    playable_ids: list[int] = metadata.get("playable_ids") or []
    if not playable_ids:
        print(f"no playable_ids in {metadata_path}; nothing to do")
        return

    print(f"Model:        {input_dir}")
    print(f"Vocab size:   {len(vocab)}")
    print(f"Playable (before): {len(playable_ids)}")
    print(f"Excluding POS: {sorted(excluded_pos)}")

    tok, mode = make_tokenizer()

    kept: list[int] = []
    dropped_by_pos: dict[str, list[int]] = {}
    pos_counter: Counter[str] = Counter()

    for vid in playable_ids:
        row = vocab[vid]
        word = display_word(row)
        pos = dominant_pos(word, tok, mode)
        pos_counter[pos] += 1
        if pos in excluded_pos:
            dropped_by_pos.setdefault(pos, []).append(vid)
        else:
            kept.append(vid)

    print(f"Playable (after):  {len(kept)}  ({len(kept) - len(playable_ids):+d})")
    print()
    print("POS breakdown of playable entries:")
    for pos, count in pos_counter.most_common():
        marker = "  (excluded)" if pos in excluded_pos else ""
        print(f"  {pos or '(empty)':<10} {count:>7}{marker}")

    if args.show_samples > 0:
        print()
        print("Excluded samples:")
        for pos, ids in dropped_by_pos.items():
            samples = [display_word(vocab[i]) for i in ids[: args.show_samples]]
            print(f"  {pos}: {', '.join(samples)}")

    if args.dry_run:
        print("\n(dry-run: metadata.json not modified)")
        return

    if not args.no_backup:
        backup_path = metadata_path.with_suffix(".json.bak")
        shutil.copy2(metadata_path, backup_path)
        print(f"\nBacked up old metadata to {backup_path}")

    metadata["playable_ids"] = kept
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"Wrote updated metadata to {metadata_path}")


if __name__ == "__main__":
    main()
