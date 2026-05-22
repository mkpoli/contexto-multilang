"""Tag each vocab entry with a human-readable semantic category.

Two cascading sources, easy to most expensive:

1. **UniDic POS subcategory** via SudachiPy. Catches proper nouns cleanly:
   人名 (person), 地名 (place), 固有名詞 (proper noun, generic),
   数詞 (number). Free, already in our deps, fast (~1 ms / word).

2. **WLSP / 分類語彙表DB** mid-category (中分類). Catches common nouns with
   curated Japanese semantic labels: 動物, 食料, 道具, 衣料, 機械, 身体,
   生命, 植物, 自然, 物質, 天地, etc. Downloaded lazily into
   `.cache/wlsp/`. License: CC BY-NC-SA 3.0 — our derived categories.json
   inherits it (fine for the free non-commercial game).

Writes `categories.json` next to vocab.json:
    { "<vocab_id>": "<label>", ... }

UI side then reads this and exposes it as a hint.

Usage:
    uv run game-vocab-categorize --input-dir src/lib/generated/ja-game
    uv run game-vocab-categorize --input-dir .snapshots/ja-game-old --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path

from sudachipy import dictionary, tokenizer

from game_vocab_tools.common import display_word, load_json

WLSP_BUNRUI_URL = "https://raw.githubusercontent.com/masayu-a/WLSP/master/bunruidb.txt"
WLSP_MID_URL = "https://raw.githubusercontent.com/masayu-a/WLSP/master/koumoku2.txt"

# UniDic POS-subcategory → human-readable Japanese label. Anything not matched
# falls through to the WLSP step or stays null.
UNIDIC_PROPER_NOUN_LABELS: dict[tuple[str, ...], str] = {
    ("名詞", "固有名詞", "人名"): "人名",
    ("名詞", "固有名詞", "地名"): "地名",
    ("名詞", "固有名詞", "一般"): "固有名詞",
    ("名詞", "数詞"): "数",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Attach semantic categories to a generated game's vocab.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Sources cascade in this order:\n"
            "  1. UniDic POS subcategory (proper-noun subtypes)\n"
            "  2. WLSP mid-category (semantic group for common nouns)\n\n"
            "Example:\n"
            "  uv run game-vocab-categorize --input-dir src/lib/generated/ja-game"
        ),
    )
    parser.add_argument("--input-dir", required=True, help="Path to a generated model directory.")
    parser.add_argument(
        "--no-unidic",
        action="store_true",
        help="Skip UniDic POS-based proper-noun classification.",
    )
    parser.add_argument(
        "--no-wlsp",
        action="store_true",
        help="Skip WLSP mid-category classification for common nouns.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(Path(".cache/wlsp").resolve()),
        help="Directory for cached WLSP downloads (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print breakdown without writing categories.json.",
    )
    parser.add_argument(
        "--show-samples",
        type=int,
        default=6,
        help="Sample words per category to print (default: %(default)s).",
    )
    return parser


# ---------- WLSP loader ----------

def _download(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        data = resp.read()
    dest.write_bytes(data)
    return data


def _read_sjis(path: Path) -> str:
    return path.read_bytes().decode("cp932")


def load_wlsp_index(cache_dir: Path) -> dict[str, str]:
    """Returns {headword: mid-category label} mapping built from WLSP DB."""
    bunrui_path = cache_dir / "bunruidb.txt"
    mid_path = cache_dir / "koumoku2.txt"
    _download(WLSP_BUNRUI_URL, bunrui_path)
    _download(WLSP_MID_URL, mid_path)

    # koumoku2: "<code 2-digit>,<label>,<count>"
    mid_labels: dict[str, str] = {}
    for line in _read_sjis(mid_path).splitlines():
        parts = line.split(",")
        if len(parts) >= 2:
            code = parts[0].strip()
            label = parts[1].strip()
            if code and label:
                mid_labels[code] = label

    # bunruidb columns (1-indexed):
    #   1=record_id, 2=entry_id, 3=type, 4=top, 5=part, 6=mid, 7=group,
    #   8=class_code (e.g. 1.5050), 9-11=paragraph/word ids, 12=headword w/ reading,
    #   13=headword body, 14=reading, 15=reverse reading
    # We index on column 13 (clean headword), value is the 2-digit mid label.
    word_to_label: dict[str, str] = {}
    # If a headword appears in multiple categories, we keep the first occurrence —
    # rows are ordered by class code, so earlier rows tend to be the more general
    # (and more useful) sense.
    for line in _read_sjis(bunrui_path).splitlines():
        cols = line.split(",")
        if len(cols) < 13:
            continue
        record_type = cols[2]
        # Skip non-main / derived entries
        if record_type not in {"A", "B"}:
            continue
        class_code = cols[7]
        headword = cols[12].strip()
        if not headword or not class_code:
            continue
        # Map 1.5050 -> 1.50 (top-1-digit + next-2-digits)
        prefix = class_code[:4] if "." in class_code else class_code
        if len(prefix) < 4:
            continue
        label = mid_labels.get(prefix)
        if not label:
            continue
        word_to_label.setdefault(headword, label)

    return word_to_label


# ---------- UniDic POS classifier ----------

def make_tokenizer():
    tok = dictionary.Dictionary().create()
    return tok, tokenizer.Tokenizer.SplitMode.C


def unidic_category(word: str, tok, mode) -> str | None:
    morphemes = list(tok.tokenize(word, mode))
    if not morphemes:
        return None
    head = max(morphemes, key=lambda m: len(m.surface()))
    pos_tuple = tuple(p for p in head.part_of_speech() if p and p != "*")
    # Try most-specific prefix first.
    for length in (3, 2):
        prefix = pos_tuple[:length]
        if prefix in UNIDIC_PROPER_NOUN_LABELS:
            return UNIDIC_PROPER_NOUN_LABELS[prefix]
    return None


# ---------- main ----------

def main() -> None:
    args = build_parser().parse_args()
    input_dir = Path(args.input_dir).resolve()
    vocab_path = input_dir / "vocab.json"
    out_path = input_dir / "categories.json"
    vocab = load_json(vocab_path)

    print(f"Model:      {input_dir}")
    print(f"Vocab size: {len(vocab)}")

    wlsp_index: dict[str, str] = {}
    if not args.no_wlsp:
        print("Loading WLSP …")
        wlsp_index = load_wlsp_index(Path(args.cache_dir))
        print(f"  WLSP entries: {len(wlsp_index)}")

    tok = mode = None
    if not args.no_unidic:
        tok, mode = make_tokenizer()

    categories: dict[str, str] = {}
    source_counter: Counter[str] = Counter()
    label_counter: Counter[str] = Counter()
    label_samples: dict[str, list[str]] = {}

    for idx, row in enumerate(vocab):
        word = display_word(row)
        label: str | None = None
        source: str = "none"

        if tok is not None:
            cat = unidic_category(word, tok, mode)
            if cat:
                label = cat
                source = "unidic"

        if label is None and wlsp_index:
            cat = wlsp_index.get(word)
            if cat:
                label = cat
                source = "wlsp"

        source_counter[source] += 1
        if label:
            categories[str(idx)] = label
            label_counter[label] += 1
            label_samples.setdefault(label, [])
            if len(label_samples[label]) < args.show_samples:
                label_samples[label].append(word)

    coverage = len(categories) / max(1, len(vocab))
    print()
    print(f"Categorized: {len(categories)} / {len(vocab)}  ({coverage:.1%})")
    print(f"  by source: {dict(source_counter)}")
    print()
    print("Top categories:")
    for label, count in label_counter.most_common(20):
        samples = ", ".join(label_samples[label])
        print(f"  {label:<10} {count:>6}  e.g. {samples}")

    if args.dry_run:
        print("\n(dry-run: categories.json not written)")
        return

    out_path.write_text(
        json.dumps(categories, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
