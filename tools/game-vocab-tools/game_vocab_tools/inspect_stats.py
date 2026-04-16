from __future__ import annotations

import argparse

import numpy as np

from game_vocab_tools.common import (
    display_word,
    load_vocab_bundle,
    ordered_vocab,
    parse_rank_values,
    resolve_input_dir,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect generated game vocab stats and cutoff ranks."
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
        "--rank-samples",
        default=None,
        help="Comma-separated rank positions to inspect from the built vocab frequency list.",
    )
    parser.add_argument(
        "--rank-windows",
        default=None,
        help="Comma-separated cutoff ranks to inspect with surrounding rows, e.g. 10000,20000,30000.",
    )
    parser.add_argument(
        "--window-radius",
        type=int,
        default=10,
        help="How many rows before and after each rank window center to print.",
    )
    return parser


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
    for index, row in enumerate(ordered_vocab(vocab)[:limit], start=1):
        print(
            f"{index:>2}. {display_word(row)}"
            f"  count={row['count']} doc_frequency={row['doc_frequency']}"
        )


def print_rank_samples(vocab: list[dict], ranks: list[int]) -> None:
    if not ranks:
        return
    ranked_vocab = ordered_vocab(vocab)
    print("\nRank samples")
    for rank in ranks:
        if rank > len(ranked_vocab):
            print(f"{rank:>6}: out of range (only {len(ranked_vocab)} rows)")
            continue
        row = ranked_vocab[rank - 1]
        print(
            f"{rank:>6}: {display_word(row)}"
            f"  count={row['count']} doc_frequency={row['doc_frequency']}"
        )

    print("\nCutoff summary")
    print(" rank  min_count_at_rank  min_doc_freq_at_rank")
    for rank in ranks:
        if rank > len(ranked_vocab):
            continue
        row = ranked_vocab[rank - 1]
        print(f" {rank:>5} {row['count']:>18} {row['doc_frequency']:>21}")


def print_rank_windows(vocab: list[dict], centers: list[int], radius: int) -> None:
    if not centers:
        return
    ranked_vocab = ordered_vocab(vocab)
    for center in centers:
        print(f"\nWindow around rank {center}")
        if center > len(ranked_vocab):
            print(f"  out of range (only {len(ranked_vocab)} rows)")
            continue
        start = max(1, center - radius)
        end = min(len(ranked_vocab), center + radius)
        for rank in range(start, end + 1):
            row = ranked_vocab[rank - 1]
            marker = "<-- cutoff" if rank == center else ""
            print(
                f"{rank:>6}. {display_word(row)}"
                f"  count={row['count']} doc_frequency={row['doc_frequency']} {marker}".rstrip()
            )


def main() -> None:
    args = build_parser().parse_args()
    input_dir = resolve_input_dir(args.game, args.input_dir)
    metadata, vocab = load_vocab_bundle(input_dir)

    print(f"Loaded game vocab from {input_dir}")
    print_stats(metadata, vocab)
    print_top_frequency(vocab, args.top_freq)
    print_rank_samples(vocab, parse_rank_values(args.rank_samples))
    print_rank_windows(vocab, parse_rank_values(args.rank_windows), args.window_radius)


if __name__ == "__main__":
    main()
