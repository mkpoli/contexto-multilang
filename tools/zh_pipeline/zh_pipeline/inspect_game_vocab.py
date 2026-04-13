from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


DEFAULT_ROOT = Path("../../src/lib/generated")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect generated game vocab, counts, and nearest neighbors."
    )
    parser.add_argument(
        "words",
        nargs="*",
        help="Optional query words to inspect.",
    )
    parser.add_argument(
        "--game",
        choices=["zh", "ja"],
        default="zh",
        help="Which generated game index to inspect.",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Override the generated game directory instead of --game.",
    )
    parser.add_argument(
        "--top-freq",
        type=int,
        default=20,
        help="How many most-frequent words to print.",
    )
    parser.add_argument(
        "--top-neighbors",
        type=int,
        default=12,
        help="How many nearest neighbors to print per query word.",
    )
    parser.add_argument(
        "--contains",
        action="store_true",
        help="If an exact word is missing, also print substring matches.",
    )
    parser.add_argument(
        "--skip-top-freq",
        action="store_true",
        help="Skip printing the top-frequency list.",
    )
    return parser


def resolve_input_dir(args: argparse.Namespace) -> Path:
    if args.input_dir:
        return Path(args.input_dir).resolve()
    return (DEFAULT_ROOT / f"{args.game}-game").resolve()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_embeddings(
    input_dir: Path, chunk_count: int, embedding_dim: int
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for index in range(chunk_count):
        chunk_path = input_dir / f"embeddings.f32.{index}.bin"
        chunk = np.fromfile(chunk_path, dtype=np.float32)
        if chunk.size % embedding_dim != 0:
            raise ValueError(f"Embedding chunk has unexpected size: {chunk_path}")
        chunks.append(chunk.reshape((-1, embedding_dim)))
    return np.vstack(chunks)


def display_word(row: dict) -> str:
    return row.get("display_word") or row["word"]


def print_stats(metadata: dict, vocab: list[dict]) -> None:
    print(f"vocab_size={metadata['vocab_size']}")
    print(f"embedding_dim={metadata['embedding_dim']}")
    print(f"playable_answers={len(metadata.get('playable_ids', []))}")
    print(f"total_pages={metadata.get('total_pages', 'unknown')}")
    print(f"explained_variance={metadata.get('explained_variance', 0):.4f}")
    if vocab:
        counts = [row["count"] for row in vocab]
        doc_freqs = [row["doc_frequency"] for row in vocab]
        print(f"max_count={max(counts)}")
        print(f"median_count={int(np.median(counts))}")
        print(f"max_doc_frequency={max(doc_freqs)}")


def print_top_frequency(vocab: list[dict], limit: int) -> None:
    print(f"\nTop {limit} by frequency")
    ordered = sorted(
        vocab,
        key=lambda row: (-row["count"], -row["doc_frequency"], row["word"]),
    )[:limit]
    for index, row in enumerate(ordered, start=1):
        print(
            f"{index:>2}. {display_word(row)}"
            f"  count={row['count']} doc_frequency={row['doc_frequency']}"
        )


def print_contains_matches(word: str, vocab: list[dict], limit: int = 12) -> None:
    matches = [
        display_word(row)
        for row in vocab
        if word in row["word"] or word in display_word(row)
    ]
    if not matches:
        print("  no substring matches")
        return
    print("  substring matches:")
    for match in matches[:limit]:
        print(f"    - {match}")


def resolve_query_ids(
    word: str, word_to_id: dict[str, int], variants: dict[str, list[int]]
) -> list[int]:
    variant_ids = variants.get(word)
    if variant_ids:
        return variant_ids
    exact_id = word_to_id.get(word)
    return [] if exact_id is None else [exact_id]


def print_word_neighbors(
    query_word: str,
    chosen_id: int,
    vocab: list[dict],
    embeddings: np.ndarray,
    top_k: int,
) -> None:
    row = vocab[chosen_id]
    scores = embeddings @ embeddings[chosen_id]
    ranking = np.argsort(-scores, kind="stable")

    print(f"\n{query_word}")
    print(
        f"canonical={display_word(row)} count={row['count']} doc_frequency={row['doc_frequency']}"
    )
    print("neighbors:")

    shown = 0
    for rank_index, neighbor_id in enumerate(ranking, start=1):
        if neighbor_id == chosen_id:
            continue
        neighbor = vocab[int(neighbor_id)]
        print(
            f"  {rank_index:>2}. {display_word(neighbor)}"
            f"  score={float(scores[neighbor_id]):.6f}"
            f" count={neighbor['count']} df={neighbor['doc_frequency']}"
        )
        shown += 1
        if shown >= top_k:
            break


def main() -> None:
    args = build_parser().parse_args()
    input_dir = resolve_input_dir(args)
    metadata = load_json(input_dir / "metadata.json")
    vocab = load_json(input_dir / "vocab.json")
    variants = load_json(input_dir / "variants.json")
    embeddings = load_embeddings(
        input_dir,
        chunk_count=metadata.get("embed_chunks", 1),
        embedding_dim=metadata["embedding_dim"],
    )
    word_to_id = {row["word"]: index for index, row in enumerate(vocab)}

    print(f"Loaded game vocab from {input_dir}")
    print_stats(metadata, vocab)

    if not args.skip_top_freq:
        print_top_frequency(vocab, args.top_freq)

    for word in args.words:
        candidate_ids = resolve_query_ids(word, word_to_id, variants)
        if not candidate_ids:
            print(f"\n{word}")
            print("  exact row not found")
            if args.contains:
                print_contains_matches(word, vocab)
            continue

        chosen_id = min(candidate_ids, key=lambda index: vocab[index]["word"])
        print_word_neighbors(word, chosen_id, vocab, embeddings, args.top_neighbors)


if __name__ == "__main__":
    main()
