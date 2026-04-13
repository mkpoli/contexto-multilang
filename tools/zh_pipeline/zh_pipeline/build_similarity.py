from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import sparse

from .constants import (
    DEFAULT_DATA_DIR,
    DEFAULT_OUTPUT_NAME,
    DEFAULT_SIMILARITY_NAME,
    DEFAULT_STOPWORDS_DIR,
)
from .timing import format_seconds, iter_progress, timed_step


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build sparse semantic similarity rows from segmented Chinese pages."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_OUTPUT_NAME),
        help="Path to the segmented JSONL file.",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_SIMILARITY_NAME),
        help="Path where similarity JSONL rows should be written.",
    )
    parser.add_argument(
        "--stopwords-dir",
        default=str(DEFAULT_STOPWORDS_DIR),
        help="Directory containing downloaded stopword txt files.",
    )
    parser.add_argument("--limit-pages", type=int, default=None)
    parser.add_argument("--min-count", type=int, default=20)
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-doc-ratio", type=float, default=0.2)
    parser.add_argument("--max-vocab", type=int, default=5000)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--chunk-size", type=int, default=128)
    return parser


def load_stopwords(stopwords_dir: Path) -> set[str]:
    if not stopwords_dir.exists():
        raise FileNotFoundError(
            f"Stopwords directory not found: {stopwords_dir}. Run `uv run zh-download-stopwords` first."
        )

    stopwords: set[str] = set()
    files = sorted(stopwords_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(
            f"No stopword files found in {stopwords_dir}. Run `uv run zh-download-stopwords` first."
        )

    for file_path in files:
        with file_path.open("r", encoding="utf-8") as source:
            for line in source:
                word = line.strip()
                if word:
                    stopwords.add(word)

    return stopwords


def iter_segmented_pages(input_path: Path, limit_pages: int | None = None):
    with input_path.open("r", encoding="utf-8") as source:
        for index, line in enumerate(source):
            if limit_pages is not None and index >= limit_pages:
                break
            if not line.strip():
                continue
            yield json.loads(line)


def normalize_token(token: str, min_length: int, stopwords: set[str]) -> str | None:
    token = token.strip()
    if len(token) < min_length:
        return None
    if token in stopwords:
        return None
    return token


def collect_counts(
    input_path: Path,
    *,
    limit_pages: int | None,
    min_length: int,
    stopwords: set[str],
):
    term_frequency: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    total_pages = 0

    for page in iter_progress(
        iter_segmented_pages(input_path, limit_pages),
        total=limit_pages,
        title="Counting vocabulary",
    ):
        total_pages += 1
        tokens: list[str] = []
        page_seen: set[str] = set()
        for raw_token in page.get("title_tokens", []):
            token = normalize_token(raw_token, min_length, stopwords)
            if token is None:
                continue
            tokens.append(token)
            page_seen.add(token)
        for raw_token in page.get("text_tokens", []):
            token = normalize_token(raw_token, min_length, stopwords)
            if token is None:
                continue
            tokens.append(token)
            page_seen.add(token)
        if not tokens:
            continue
        term_frequency.update(tokens)
        document_frequency.update(page_seen)

    return term_frequency, document_frequency, total_pages


def build_vocab(
    term_frequency: Counter[str],
    document_frequency: Counter[str],
    *,
    total_pages: int,
    min_count: int,
    max_doc_ratio: float,
    max_vocab: int,
) -> dict[str, dict[str, int]]:
    candidates = []
    for token, count in term_frequency.items():
        if count < min_count:
            continue
        doc_freq = document_frequency[token]
        if total_pages and (doc_freq / total_pages) > max_doc_ratio:
            continue
        candidates.append((token, count, doc_freq))

    candidates.sort(key=lambda item: (-item[1], item[0]))
    selected = candidates[:max_vocab]
    return {
        token: {"count": count, "doc_frequency": doc_freq}
        for token, count, doc_freq in selected
    }


def build_cooccurrence(
    input_path: Path,
    *,
    vocab_tokens: list[str],
    limit_pages: int | None,
    min_length: int,
    stopwords: set[str],
    window_size: int,
) -> list[Counter[int]]:
    token_to_index = {token: index for index, token in enumerate(vocab_tokens)}
    vectors = [Counter() for _ in vocab_tokens]

    for page in iter_progress(
        iter_segmented_pages(input_path, limit_pages),
        total=limit_pages,
        title="Building cooccurrence",
    ):
        token_ids: list[int] = []
        for raw_token in page.get("text_tokens", []):
            token = normalize_token(raw_token, min_length, stopwords)
            if token is None:
                continue
            token_index = token_to_index.get(token)
            if token_index is not None:
                token_ids.append(token_index)

        for index, token_id in enumerate(token_ids):
            left = max(0, index - window_size)
            right = min(len(token_ids), index + window_size + 1)
            row = vectors[token_id]
            for neighbor_index in range(left, right):
                if neighbor_index == index:
                    continue
                neighbor_id = token_ids[neighbor_index]
                if neighbor_id == token_id:
                    continue
                row[neighbor_id] += 1

    return vectors


def build_weighted_matrix(
    vectors: list[Counter[int]],
    vocab_tokens: list[str],
) -> tuple[sparse.csr_matrix, list[str]]:
    row_indices: list[int] = []
    col_indices: list[int] = []
    data: list[float] = []
    kept_tokens: list[str] = []

    for token_index, counter in enumerate(vectors):
        if not counter:
            continue

        row_index = len(kept_tokens)
        kept_tokens.append(vocab_tokens[token_index])

        for context_index, count in counter.items():
            row_indices.append(row_index)
            col_indices.append(context_index)
            data.append(math.log1p(count))

    matrix = sparse.coo_matrix(
        (data, (row_indices, col_indices)),
        shape=(len(kept_tokens), len(vocab_tokens)),
        dtype=np.float32,
    ).tocsr()
    matrix.sum_duplicates()
    return matrix, kept_tokens


def normalize_rows(matrix: sparse.csr_matrix) -> sparse.csr_matrix:
    norms = np.sqrt(matrix.multiply(matrix).sum(axis=1)).A1
    nonzero_rows = norms > 0
    scale = np.zeros_like(norms, dtype=np.float32)
    scale[nonzero_rows] = 1.0 / norms[nonzero_rows]
    return sparse.diags(scale).dot(matrix).tocsr()


def iter_similarity_rows(
    normalized_matrix: sparse.csr_matrix,
    kept_tokens: list[str],
    vocab_meta: dict[str, dict[str, int]],
    *,
    top_k: int,
    chunk_size: int,
):
    total_tokens = len(kept_tokens)

    for start in iter_progress(
        range(0, total_tokens, chunk_size),
        total=(total_tokens + chunk_size - 1) // chunk_size,
        title="Scoring similarities",
    ):
        end = min(start + chunk_size, total_tokens)
        similarity_chunk = (normalized_matrix[start:end] @ normalized_matrix.T).tocsr()

        for local_index, token in enumerate(kept_tokens[start:end]):
            global_index = start + local_index
            row = similarity_chunk.getrow(local_index)
            row_indices = row.indices
            row_scores = row.data

            if row_scores.size == 0:
                neighbors = []
            else:
                mask = row_indices != global_index
                row_indices = row_indices[mask]
                row_scores = row_scores[mask]

                positive_mask = row_scores > 0
                row_indices = row_indices[positive_mask]
                row_scores = row_scores[positive_mask]

                if row_scores.size == 0:
                    neighbors = []
                else:
                    limit = min(top_k, row_scores.size)
                    candidate_indices = np.argpartition(-row_scores, limit - 1)[:limit]
                    pairs = [
                        (kept_tokens[row_indices[index]], float(row_scores[index]))
                        for index in candidate_indices
                    ]
                    pairs.sort(key=lambda item: (-item[1], item[0]))

                    neighbors = [
                        {
                            "word": neighbor_word,
                            "score": round(score, 6),
                            "rank": rank,
                        }
                        for rank, (neighbor_word, score) in enumerate(pairs, start=1)
                    ]

            yield {
                "word": token,
                "count": vocab_meta[token]["count"],
                "doc_frequency": vocab_meta[token]["doc_frequency"],
                "neighbors": neighbors,
            }


def main() -> None:
    total_start = __import__("time").perf_counter()
    timings: dict[str, float] = {}
    args = build_parser().parse_args()
    input_path = Path(args.input_path).resolve()
    output_path = Path(args.output_path).resolve()
    stopwords_dir = Path(args.stopwords_dir).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    with timed_step("normalize matrix", timings):
        normalized_matrix = normalize_rows(weighted_matrix)

    written = 0
    with timed_step("score and write rows", timings):
        with output_path.open("w", encoding="utf-8") as target:
            for row in iter_similarity_rows(
                normalized_matrix,
                kept_tokens,
                vocab_meta,
                top_k=args.top_k,
                chunk_size=args.chunk_size,
            ):
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

    print(f"Pages counted: {total_pages}")
    print(f"Stopwords loaded: {len(stopwords)}")
    print(f"Vocabulary size: {len(vocab_meta)}")
    print(f"Similarity rows written: {written}")
    print(f"Output: {output_path}")
    print("Timing summary:")
    for label, elapsed in timings.items():
        print(f"- {label}: {format_seconds(elapsed)}")
    print(f"- total: {format_seconds(__import__('time').perf_counter() - total_start)}")


if __name__ == "__main__":
    main()
