"""Multi-dimensional comparison of two generated game-vocab artifact dirs.

Produces three views, all on the same pair of model directories:

1. Pipeline-internal signals from each metadata.json + vocab coverage diff.
2. Side-by-side nearest-neighbor lists for a configurable set of anchor words,
   plus Jaccard overlap of the top-K neighbor sets.
3. Spearman correlation against the Sakaizawa-Komachi Japanese Word Similarity
   Dataset (tmu-nlp/JapaneseWordSimilarityDataset, score_{noun,verb,adv,adj}.csv).

Usage:
    uv run game-vocab-compare \
        --old .snapshots/ja-game-old \
        --new src/lib/generated/ja-game
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from game_vocab_tools.common import (
    display_word,
    load_embeddings,
    load_json,
    load_vocab_bundle,
    resolve_query_ids,
)

JWS_BASE_URL = (
    "https://raw.githubusercontent.com/tmu-nlp/JapaneseWordSimilarityDataset/master"
)
JWS_PARTS = ("noun", "verb", "adv", "adj")

DEFAULT_ANCHORS = [
    "音楽",
    "季節",
    "学校",
    "歴史",
    "政治",
    "料理",
    "病院",
    "言葉",
    "感情",
    "技術",
    "自然",
    "動物",
    "家族",
    "宇宙",
    "戦争",
]


@dataclass
class Model:
    label: str
    input_dir: Path
    metadata: dict
    vocab: list[dict]
    variants: dict[str, list[int]]
    embeddings: np.ndarray  # already L2-normalized rows
    word_to_id: dict[str, int]

    @classmethod
    def load(cls, label: str, input_dir: Path) -> "Model":
        metadata, vocab = load_vocab_bundle(input_dir)
        variants = load_json(input_dir / "variants.json")
        embeddings = load_embeddings(
            input_dir,
            chunk_count=metadata.get("embed_chunks", 1),
            embedding_dim=metadata["embedding_dim"],
        )
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms
        word_to_id = {row["word"]: index for index, row in enumerate(vocab)}
        return cls(
            label=label,
            input_dir=input_dir,
            metadata=metadata,
            vocab=vocab,
            variants=variants,
            embeddings=embeddings.astype(np.float32),
            word_to_id=word_to_id,
        )

    def find_id(self, word: str) -> int | None:
        ids = resolve_query_ids(word, self.word_to_id, self.variants)
        if not ids:
            return None
        return min(ids, key=lambda index: self.vocab[index]["word"])

    def neighbors(self, anchor_id: int, top_k: int) -> list[tuple[str, float]]:
        scores = self.embeddings @ self.embeddings[anchor_id]
        ranking = np.argsort(-scores, kind="stable")
        out: list[tuple[str, float]] = []
        for neighbor_id in ranking:
            if neighbor_id == anchor_id:
                continue
            out.append((display_word(self.vocab[int(neighbor_id)]), float(scores[int(neighbor_id)])))
            if len(out) >= top_k:
                break
        return out


# ---------- (1) pipeline-internal signals + coverage ----------

def section_signals(old: Model, new: Model) -> None:
    print("\n=== (1) Pipeline-internal signals ===")
    metric_keys = (
        "vocab_size",
        "embedding_dim",
        "total_pages",
        "min_count",
        "max_vocab",
        "window_size",
        "explained_variance",
        "embed_chunks",
        "token_unit",
    )
    print(f"{'metric':<22} {old.label:>22}  {new.label:>22}  delta")
    for key in metric_keys:
        a = old.metadata.get(key)
        b = new.metadata.get(key)
        delta = _delta_str(a, b)
        print(f"{key:<22} {str(a):>22}  {str(b):>22}  {delta}")

    old_set = {row["word"] for row in old.vocab}
    new_set = {row["word"] for row in new.vocab}
    inter = old_set & new_set
    only_old = old_set - new_set
    only_new = new_set - old_set
    print()
    print(f"  vocab overlap:  {len(inter):>7}")
    print(f"  only in old:    {len(only_old):>7}")
    print(f"  only in new:    {len(only_new):>7}")
    print(
        f"  jaccard:        {len(inter) / max(1, len(old_set | new_set)):.4f}"
    )

    playable_old = set(old.metadata.get("playable_ids", []))
    playable_new = set(new.metadata.get("playable_ids", []))
    print()
    print(f"  playable_ids old/new: {len(playable_old):>7} / {len(playable_new):>7}")
    print(
        f"  playable ratio:       "
        f"{len(playable_old) / max(1, old.metadata['vocab_size']):.3f} / "
        f"{len(playable_new) / max(1, new.metadata['vocab_size']):.3f}"
    )


def _delta_str(a, b) -> str:
    try:
        if a is None or b is None:
            return ""
        diff = float(b) - float(a)
        if diff == 0:
            return "·"
        sign = "+" if diff > 0 else ""
        if isinstance(a, int) and isinstance(b, int):
            return f"{sign}{int(diff)}"
        return f"{sign}{diff:.4f}"
    except (TypeError, ValueError):
        return ""


# ---------- (2) anchor-word neighbor inspection ----------

def section_neighbors(old: Model, new: Model, anchors: list[str], top_k: int) -> None:
    print(f"\n=== (2) Anchor-word nearest neighbors (top {top_k}) ===")
    overlaps: list[float] = []
    missing_old: list[str] = []
    missing_new: list[str] = []

    for anchor in anchors:
        old_id = old.find_id(anchor)
        new_id = new.find_id(anchor)
        if old_id is None:
            missing_old.append(anchor)
        if new_id is None:
            missing_new.append(anchor)
        if old_id is None or new_id is None:
            print(f"\n{anchor}: skipped (old={old_id is not None}, new={new_id is not None})")
            continue

        old_neigh = old.neighbors(old_id, top_k)
        new_neigh = new.neighbors(new_id, top_k)
        old_words = [w for w, _ in old_neigh]
        new_words = [w for w, _ in new_neigh]
        union = set(old_words) | set(new_words)
        inter = set(old_words) & set(new_words)
        jaccard = len(inter) / max(1, len(union))
        overlaps.append(jaccard)

        print(f"\n{anchor}  (jaccard top-{top_k} = {jaccard:.2f})")
        print(f"  {'#':>3} {old.label:<22} {new.label:<22}")
        for rank in range(top_k):
            o = old_words[rank] if rank < len(old_words) else ""
            n = new_words[rank] if rank < len(new_words) else ""
            mark = "  " if o == n else "≠ " if o and n else "  "
            print(f"  {rank + 1:>3} {o:<22} {mark}{n}")

    if overlaps:
        print(
            f"\n  mean jaccard across {len(overlaps)} anchors: {np.mean(overlaps):.3f}"
        )
    if missing_old:
        print(f"  OOV in {old.label}: {', '.join(missing_old)}")
    if missing_new:
        print(f"  OOV in {new.label}: {', '.join(missing_new)}")


# ---------- (3) JWS Spearman ----------

def _fetch_jws_part(part: str, cache_dir: Path | None) -> bytes:
    url = f"{JWS_BASE_URL}/score_{part}.csv"
    if cache_dir:
        cache_path = cache_dir / f"score_{part}.csv"
        if cache_path.exists():
            return cache_path.read_bytes()
        cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url} ...")
    with urllib.request.urlopen(url) as resp:  # noqa: S310 — known github URL
        data = resp.read()
    if cache_dir:
        (cache_dir / f"score_{part}.csv").write_bytes(data)
    return data


def _load_jws(cache_dir: Path | None) -> dict[str, list[tuple[str, str, float]]]:
    out: dict[str, list[tuple[str, str, float]]] = {}
    for part in JWS_PARTS:
        text = _fetch_jws_part(part, cache_dir).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        pairs: list[tuple[str, str, float]] = []
        for row in reader:
            try:
                score = float(row.get("mean(remove_extreme_annotator)") or row["mean"])
            except (TypeError, ValueError, KeyError):
                continue
            w1 = (row.get("word1") or "").strip()
            w2 = (row.get("word2") or "").strip()
            if not w1 or not w2:
                continue
            pairs.append((w1, w2, score))
        out[part] = pairs
    return out


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def _evaluate(model: Model, pairs: list[tuple[str, str, float]]) -> tuple[float, int, int]:
    human: list[float] = []
    cosine: list[float] = []
    matched = 0
    total = len(pairs)
    for w1, w2, score in pairs:
        id1 = model.find_id(w1)
        id2 = model.find_id(w2)
        if id1 is None or id2 is None or id1 == id2:
            continue
        cos = float(model.embeddings[id1] @ model.embeddings[id2])
        cosine.append(cos)
        human.append(score)
        matched += 1
    rho = _spearman(np.asarray(human), np.asarray(cosine))
    return rho, matched, total


def section_benchmark(old: Model, new: Model, cache_dir: Path | None) -> None:
    print("\n=== (3) JapaneseWordSimilarityDataset (Sakaizawa & Komachi) ===")
    print("  Spearman ρ vs. human mean (remove_extreme_annotator)")
    parts = _load_jws(cache_dir)

    print()
    print(f"  {'part':<6} {'pairs':>6}  "
          f"{old.label + ' ρ':>16} {old.label + ' cov':>14}  "
          f"{new.label + ' ρ':>16} {new.label + ' cov':>14}")
    aggregate: dict[str, list[float]] = {"old_h": [], "old_c": [], "new_h": [], "new_c": []}
    for part in JWS_PARTS:
        pairs = parts.get(part, [])
        rho_o, m_o, t = _evaluate(old, pairs)
        rho_n, m_n, _ = _evaluate(new, pairs)
        print(
            f"  {part:<6} {t:>6}  "
            f"{rho_o:>16.4f} {m_o:>10}/{t:<3}  "
            f"{rho_n:>16.4f} {m_n:>10}/{t:<3}"
        )
        # Aggregate raw pair lists for an overall Spearman.
        for w1, w2, score in pairs:
            id_o1 = old.find_id(w1)
            id_o2 = old.find_id(w2)
            if id_o1 is not None and id_o2 is not None and id_o1 != id_o2:
                aggregate["old_h"].append(score)
                aggregate["old_c"].append(float(old.embeddings[id_o1] @ old.embeddings[id_o2]))
            id_n1 = new.find_id(w1)
            id_n2 = new.find_id(w2)
            if id_n1 is not None and id_n2 is not None and id_n1 != id_n2:
                aggregate["new_h"].append(score)
                aggregate["new_c"].append(float(new.embeddings[id_n1] @ new.embeddings[id_n2]))
    rho_o_all = _spearman(np.asarray(aggregate["old_h"]), np.asarray(aggregate["old_c"]))
    rho_n_all = _spearman(np.asarray(aggregate["new_h"]), np.asarray(aggregate["new_c"]))
    total = sum(len(parts[p]) for p in JWS_PARTS)
    print(
        f"  {'all':<6} {total:>6}  "
        f"{rho_o_all:>16.4f} {len(aggregate['old_h']):>10}/{total:<3}  "
        f"{rho_n_all:>16.4f} {len(aggregate['new_h']):>10}/{total:<3}"
    )


# ---------- entry ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two generated game-vocab models on three axes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run game-vocab-compare \\\n"
            "      --old .snapshots/ja-game-old \\\n"
            "      --new src/lib/generated/ja-game"
        ),
    )
    parser.add_argument("--old", required=True, help="Path to baseline model directory.")
    parser.add_argument("--new", required=True, help="Path to candidate model directory.")
    parser.add_argument(
        "--anchors",
        default=",".join(DEFAULT_ANCHORS),
        help="Comma-separated anchor words for neighbor inspection.",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Neighbors per anchor.")
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip the JWS download / Spearman section.",
    )
    parser.add_argument(
        "--benchmark-cache",
        default=str(Path(".cache/jws").resolve()),
        help="Directory to cache downloaded JWS CSVs (default: %(default)s).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    old = Model.load("old", Path(args.old).resolve())
    new = Model.load("new", Path(args.new).resolve())
    anchors = [a.strip() for a in args.anchors.split(",") if a.strip()]
    cache_dir = Path(args.benchmark_cache) if args.benchmark_cache else None

    print(f"old model: {old.input_dir}")
    print(f"new model: {new.input_dir}")

    section_signals(old, new)
    section_neighbors(old, new, anchors, args.top_k)
    if not args.skip_benchmark:
        section_benchmark(old, new, cache_dir)


if __name__ == "__main__":
    main()
