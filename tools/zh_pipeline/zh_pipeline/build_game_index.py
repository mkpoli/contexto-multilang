from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from opencc import OpenCC
from sklearn.decomposition import TruncatedSVD

from .build_similarity import (
    build_cooccurrence,
    build_vocab,
    build_weighted_matrix,
    collect_counts,
    load_stopwords,
)
from .constants import (
    DEFAULT_DATA_DIR,
    DEFAULT_GAME_INDEX_DIR,
    DEFAULT_OUTPUT_NAME,
    DEFAULT_STOPWORDS_DIR,
)
from .timing import format_seconds, timed_step


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dense Chinese word embeddings for exact game-time ranking."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_OUTPUT_NAME),
        help="Path to the segmented JSONL file.",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_GAME_INDEX_DIR),
        help="Directory where the generated game index files should be written.",
    )
    parser.add_argument(
        "--stopwords-dir",
        default=str(DEFAULT_STOPWORDS_DIR),
        help="Directory containing downloaded stopword txt files.",
    )
    parser.add_argument("--limit-pages", type=int, default=None)
    parser.add_argument("--min-count", type=int, default=20)
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-doc-ratio", type=float, default=1.0)
    parser.add_argument("--max-vocab", type=int, default=20000)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--embedding-dim", type=int, default=256)
    parser.add_argument("--svd-iter", type=int, default=7)
    return parser


def normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return embeddings / norms


def build_variant_rows(
    words: list[str], counts: list[int], doc_frequencies: list[int]
) -> dict[str, list[int]]:
    to_traditional = OpenCC("s2t")
    to_simplified = OpenCC("t2s")
    variants: dict[str, list[int]] = {}

    priority = sorted(
        range(len(words)),
        key=lambda index: (-counts[index], -doc_frequencies[index], words[index]),
    )

    for index in priority:
        word = words[index]
        aliases = {word, to_traditional.convert(word), to_simplified.convert(word)}
        for alias in aliases:
            if not alias:
                continue
            existing = variants.setdefault(alias, [])
            if index not in existing:
                existing.append(index)

    return variants


def build_playable_mask(
    counts: list[int], doc_frequencies: list[int], words: list[str]
) -> list[int]:
    playable_ids: list[int] = []
    for index, (word, count, doc_frequency) in enumerate(
        zip(words, counts, doc_frequencies, strict=True)
    ):
        if len(word) > 4:
            continue
        if count < 30 or doc_frequency < 10:
            continue
        playable_ids.append(index)
    return playable_ids


def main() -> None:
    total_start = __import__("time").perf_counter()
    timings: dict[str, float] = {}
    args = build_parser().parse_args()
    input_path = Path(args.input_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    stopwords_dir = Path(args.stopwords_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with timed_step("load stopwords", timings):
        stopwords = load_stopwords(stopwords_dir)
    with timed_step("collect counts", timings):
        term_frequency, document_frequency, total_pages = collect_counts(
            input_path,
            limit_pages=args.limit_pages,
            min_length=args.min_length,
            stopwords=stopwords,
        )
    with timed_step("build vocabulary", timings):
        vocab_meta = build_vocab(
            term_frequency,
            document_frequency,
            total_pages=total_pages,
            min_count=args.min_count,
            max_doc_ratio=args.max_doc_ratio,
            max_vocab=args.max_vocab,
        )
    vocab_tokens = sorted(vocab_meta.keys())
    with timed_step("build cooccurrence", timings):
        vectors = build_cooccurrence(
            input_path,
            vocab_tokens=vocab_tokens,
            limit_pages=args.limit_pages,
            min_length=args.min_length,
            stopwords=stopwords,
            window_size=args.window_size,
        )

    with timed_step("build weighted matrix", timings):
        weighted_matrix, kept_tokens = build_weighted_matrix(vectors, vocab_tokens)
    embedding_dim = max(
        2,
        min(
            args.embedding_dim,
            weighted_matrix.shape[0] - 1,
            weighted_matrix.shape[1] - 1,
        ),
    )

    with timed_step("fit embedding svd", timings):
        svd = TruncatedSVD(
            n_components=embedding_dim,
            n_iter=args.svd_iter,
            random_state=0,
            algorithm="randomized",
        )
        embeddings = svd.fit_transform(weighted_matrix).astype(np.float32, copy=False)
    with timed_step("normalize embeddings", timings):
        embeddings = normalize_embeddings(embeddings).astype(np.float32, copy=False)

    counts = [vocab_meta[word]["count"] for word in kept_tokens]
    doc_frequencies = [vocab_meta[word]["doc_frequency"] for word in kept_tokens]
    with timed_step("build answer mask", timings):
        playable_ids = build_playable_mask(counts, doc_frequencies, kept_tokens)

    vocab_path = output_dir / "vocab.json"
    variants_path = output_dir / "variants.json"
    metadata_path = output_dir / "metadata.json"
    embeddings_path = output_dir / "embeddings.f32.bin"

    with timed_step("write artifacts", timings):
        to_traditional = OpenCC("s2t")
        vocab_rows = [
            {
                "word": word,
                "display_word": to_traditional.convert(word),
                "count": count,
                "doc_frequency": doc_frequency,
            }
            for word, count, doc_frequency in zip(
                kept_tokens, counts, doc_frequencies, strict=True
            )
        ]
        vocab_path.write_text(
            json.dumps(vocab_rows, ensure_ascii=False), encoding="utf-8"
        )

        variant_rows = build_variant_rows(kept_tokens, counts, doc_frequencies)
        variants_path.write_text(
            json.dumps(variant_rows, ensure_ascii=False), encoding="utf-8"
        )

        MAX_EMBED_CHUNK_BYTES = 25 * 1024 * 1024
        num_words = len(embeddings)
        bytes_per_word = embedding_dim * embeddings.dtype.itemsize
        words_per_chunk = MAX_EMBED_CHUNK_BYTES // bytes_per_word
        num_chunks = (num_words + words_per_chunk - 1) // words_per_chunk
        words_per_chunk = (num_words + num_chunks - 1) // num_chunks
        embed_chunks: list[Path] = []
        for i in range(num_chunks):
            start_word = i * words_per_chunk
            end_word = min((i + 1) * words_per_chunk, num_words)
            chunk_path = embeddings_path.with_name(f"embeddings.f32.{i}.bin")
            embeddings[start_word:end_word].tofile(chunk_path)
            embed_chunks.append(chunk_path)

        metadata = {
            "vocab_size": len(kept_tokens),
            "embedding_dim": embedding_dim,
            "playable_ids": playable_ids,
            "total_pages": total_pages,
            "min_count": args.min_count,
            "max_vocab": args.max_vocab,
            "window_size": args.window_size,
            "explained_variance": float(svd.explained_variance_ratio_.sum()),
            "embed_chunks": num_chunks,
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Embeddings split into {num_chunks} chunk(s) (max 25 MiB each)")

    print(f"Pages counted: {total_pages}")
    print(f"Stopwords loaded: {len(stopwords)}")
    print(f"Vocabulary size: {len(kept_tokens)}")
    print(f"Embedding dim: {embedding_dim}")
    print(f"Playable answers: {len(playable_ids)}")
    print(f"Explained variance: {svd.explained_variance_ratio_.sum():.4f}")
    print(f"Output dir: {output_dir}")
    print("Timing summary:")
    for label, elapsed in timings.items():
        print(f"- {label}: {format_seconds(elapsed)}")
    print(f"- total: {format_seconds(__import__('time').perf_counter() - total_start)}")


if __name__ == "__main__":
    main()
