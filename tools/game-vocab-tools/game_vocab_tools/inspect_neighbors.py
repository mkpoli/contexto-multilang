from __future__ import annotations

import argparse

import numpy as np

from game_vocab_tools.common import (
    display_word,
    load_embeddings,
    load_json,
    load_vocab_bundle,
    resolve_input_dir,
    resolve_query_ids,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect generated game vocab nearest neighbors."
    )
    parser.add_argument(
        "words",
        nargs="+",
        help="Query words to inspect.",
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
    return parser


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
    input_dir = resolve_input_dir(args.game, args.input_dir)
    metadata, vocab = load_vocab_bundle(input_dir)
    variants = load_json(input_dir / "variants.json")
    embeddings = load_embeddings(
        input_dir,
        chunk_count=metadata.get("embed_chunks", 1),
        embedding_dim=metadata["embedding_dim"],
    )
    word_to_id = {row["word"]: index for index, row in enumerate(vocab)}

    print(f"Loaded game vocab from {input_dir}")
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
