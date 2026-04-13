from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD

from .build_game_index import normalize_embeddings
from .build_similarity import build_vocab, load_stopwords
from .ja_constants import DEFAULT_DATA_DIR, DEFAULT_DICTIONARY_PATH
from .ja_tokenizer import iter_tokenized_pages, init_tokenizer
from .timing import format_seconds, iter_progress, timed_step


DEFAULT_GAME_INDEX_DIR = Path("../../src/lib/generated/ja-game")
MAX_EMBED_CHUNK_BYTES = 25 * 1024 * 1024
PAGE_RANGE_PATTERN = re.compile(r"\.xml-p(\d+)p(\d+)(?:\.bz2)?$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dense Japanese lemma embeddings directly from Wikimedia XML or bz2 shards."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(
            DEFAULT_DATA_DIR / "jawiki-latest-pages-articles1.xml-p1p114794.bz2"
        ),
        help="Path to one XML or bz2 dump shard in single-file mode.",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_GAME_INDEX_DIR),
        help="Directory where the generated game index files should be written.",
    )
    parser.add_argument(
        "--all-pages-articles-shards",
        action="store_true",
        help="Build from every jawiki pages-articles shard found in the input directory.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory to scan in batch mode.",
    )
    parser.add_argument(
        "--dictionary",
        default=str(DEFAULT_DICTIONARY_PATH),
        help="Path to a Vibrato system dictionary (.dic or .dic.zst).",
    )
    parser.add_argument(
        "--stopwords-dir",
        default=str(DEFAULT_DATA_DIR / "stopwords"),
        help="Directory containing Japanese stopword txt files.",
    )
    parser.add_argument("--limit-pages", type=int, default=None)
    parser.add_argument("--min-count", type=int, default=20)
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-doc-ratio", type=float, default=0.2)
    parser.add_argument("--max-vocab", type=int, default=20000)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--embedding-dim", type=int, default=256)
    parser.add_argument("--svd-iter", type=int, default=7)
    return parser


def resolve_inputs(args: argparse.Namespace) -> list[Path]:
    if args.all_pages_articles_shards:
        input_dir = Path(args.input_dir).resolve()
        inputs = sorted(input_dir.glob("jawiki-latest-pages-articles*.bz2"))
        if not inputs:
            inputs = sorted(
                path
                for path in input_dir.glob("jawiki-latest-pages-articles*")
                if path.is_file() and path.suffix not in {".jsonl", ".txt"}
            )
        if not inputs:
            raise FileNotFoundError(
                f"No jawiki pages-articles shards found in {input_dir}"
            )
        return inputs
    return [Path(args.input_path).resolve()]


def normalize_token(token: str, min_length: int, stopwords: set[str]) -> str | None:
    token = token.strip()
    if len(token) < min_length:
        return None
    if token in stopwords:
        return None
    return token


def estimate_pages_in_path(input_path: Path) -> int | None:
    match = PAGE_RANGE_PATTERN.search(input_path.name)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end < start:
        return None
    return end - start + 1


def estimate_total_pages(
    input_paths: list[Path], limit_pages: int | None
) -> int | None:
    if limit_pages is not None:
        return limit_pages
    estimates = [estimate_pages_in_path(path) for path in input_paths]
    if any(estimate is None for estimate in estimates):
        return None
    return sum(estimate for estimate in estimates if estimate is not None)


def iter_all_pages(input_paths: list[Path]):
    for input_path in input_paths:
        yield from iter_tokenized_pages(input_path)


def collect_counts_from_inputs(
    input_paths: list[Path],
    *,
    limit_pages: int | None,
    min_length: int,
    stopwords: set[str],
    progress_total: int | None,
):
    term_frequency: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    total_pages = 0

    for page in iter_progress(
        iter_all_pages(input_paths),
        total=progress_total,
        title="Counting Japanese vocabulary",
    ):
        if limit_pages is not None and total_pages >= limit_pages:
            break
        total_pages += 1
        tokens: list[str] = []
        page_seen: set[str] = set()
        for _, raw_token in page["title_pairs"]:
            token = normalize_token(raw_token, min_length, stopwords)
            if token is None:
                continue
            tokens.append(token)
            page_seen.add(token)
        for _, raw_token in page["text_pairs"]:
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


def build_cooccurrence_and_variants(
    input_paths: list[Path],
    *,
    vocab_tokens: list[str],
    limit_pages: int | None,
    min_length: int,
    stopwords: set[str],
    window_size: int,
    counts: list[int],
    doc_frequencies: list[int],
    progress_total: int | None,
):
    token_to_index = {token: index for index, token in enumerate(vocab_tokens)}
    vectors = [Counter() for _ in vocab_tokens]
    alias_to_ids: dict[str, set[int]] = defaultdict(set)
    processed_pages = 0

    for page in iter_progress(
        iter_all_pages(input_paths),
        total=progress_total,
        title="Building Japanese cooccurrence",
    ):
        if limit_pages is not None and processed_pages >= limit_pages:
            break
        processed_pages += 1

        for surface, lemma in page["title_pairs"]:
            token = normalize_token(lemma, min_length, stopwords)
            if token is None:
                continue
            token_id = token_to_index.get(token)
            if token_id is None:
                continue
            alias_to_ids[token].add(token_id)
            alias_to_ids[surface].add(token_id)

        token_ids: list[int] = []
        for surface, lemma in page["text_pairs"]:
            token = normalize_token(lemma, min_length, stopwords)
            if token is None:
                continue
            token_id = token_to_index.get(token)
            if token_id is None:
                continue
            alias_to_ids[token].add(token_id)
            alias_to_ids[surface].add(token_id)
            token_ids.append(token_id)

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

    priority = sorted(
        range(len(vocab_tokens)),
        key=lambda index: (
            -counts[index],
            -doc_frequencies[index],
            vocab_tokens[index],
        ),
    )
    rank = {token_id: order for order, token_id in enumerate(priority)}
    variants = {
        alias: sorted(token_ids, key=lambda token_id: rank[token_id])
        for alias, token_ids in alias_to_ids.items()
        if alias.strip()
    }
    return vectors, variants


def build_weighted_matrix(vectors: list[Counter[int]], vocab_tokens: list[str]):
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
            data.append(np.log1p(count))

    from scipy import sparse

    matrix = sparse.coo_matrix(
        (data, (row_indices, col_indices)),
        shape=(len(kept_tokens), len(vocab_tokens)),
        dtype=np.float32,
    ).tocsr()
    matrix.sum_duplicates()
    return matrix, kept_tokens


def build_playable_mask(
    counts: list[int], doc_frequencies: list[int], words: list[str]
) -> list[int]:
    playable_ids: list[int] = []
    for index, (word, count, doc_frequency) in enumerate(
        zip(words, counts, doc_frequencies, strict=True)
    ):
        if len(word) > 8:
            continue
        if count < 30 or doc_frequency < 10:
            continue
        playable_ids.append(index)
    return playable_ids


def write_embedding_chunks(
    output_dir: Path, embeddings: np.ndarray, embedding_dim: int
) -> int:
    num_words = len(embeddings)
    bytes_per_word = embedding_dim * embeddings.dtype.itemsize
    words_per_chunk = max(1, MAX_EMBED_CHUNK_BYTES // bytes_per_word)
    num_chunks = (num_words + words_per_chunk - 1) // words_per_chunk
    words_per_chunk = (num_words + num_chunks - 1) // num_chunks
    for i in range(num_chunks):
        start_word = i * words_per_chunk
        end_word = min((i + 1) * words_per_chunk, num_words)
        chunk_path = output_dir / f"embeddings.f32.{i}.bin"
        embeddings[start_word:end_word].tofile(chunk_path)
    return num_chunks


def main() -> None:
    total_start = time.perf_counter()
    timings: dict[str, float] = {}
    args = build_parser().parse_args()
    input_paths = resolve_inputs(args)
    output_dir = Path(args.output_dir).resolve()
    dictionary_path = Path(args.dictionary).resolve()
    stopwords_dir = Path(args.stopwords_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_total = estimate_total_pages(input_paths, args.limit_pages)

    init_tokenizer(dictionary_path)

    with timed_step("load stopwords", timings):
        stopwords = load_stopwords(stopwords_dir)
    with timed_step("collect counts", timings):
        term_frequency, document_frequency, total_pages = collect_counts_from_inputs(
            input_paths,
            limit_pages=args.limit_pages,
            min_length=args.min_length,
            stopwords=stopwords,
            progress_total=progress_total,
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
    counts = [vocab_meta[word]["count"] for word in vocab_tokens]
    doc_frequencies = [vocab_meta[word]["doc_frequency"] for word in vocab_tokens]
    with timed_step("build cooccurrence", timings):
        vectors, variants = build_cooccurrence_and_variants(
            input_paths,
            vocab_tokens=vocab_tokens,
            limit_pages=args.limit_pages,
            min_length=args.min_length,
            stopwords=stopwords,
            window_size=args.window_size,
            counts=counts,
            doc_frequencies=doc_frequencies,
            progress_total=progress_total,
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

    kept_set = set(kept_tokens)
    kept_counts = [vocab_meta[word]["count"] for word in kept_tokens]
    kept_doc_frequencies = [vocab_meta[word]["doc_frequency"] for word in kept_tokens]
    with timed_step("filter variants", timings):
        kept_token_to_new_index = {
            token: index for index, token in enumerate(kept_tokens)
        }
        variants = {
            alias: [
                kept_token_to_new_index[vocab_tokens[token_id]]
                for token_id in token_ids
                if vocab_tokens[token_id] in kept_set
            ]
            for alias, token_ids in variants.items()
        }
        variants = {alias: ids for alias, ids in variants.items() if ids}
    with timed_step("build answer mask", timings):
        playable_ids = build_playable_mask(
            kept_counts, kept_doc_frequencies, kept_tokens
        )

    with timed_step("write artifacts", timings):
        vocab_rows = [
            {
                "word": word,
                "display_word": word,
                "count": count,
                "doc_frequency": doc_frequency,
            }
            for word, count, doc_frequency in zip(
                kept_tokens, kept_counts, kept_doc_frequencies, strict=True
            )
        ]
        (output_dir / "vocab.json").write_text(
            json.dumps(vocab_rows, ensure_ascii=False), encoding="utf-8"
        )
        (output_dir / "variants.json").write_text(
            json.dumps(variants, ensure_ascii=False), encoding="utf-8"
        )
        embed_chunks = write_embedding_chunks(output_dir, embeddings, embedding_dim)
        metadata = {
            "vocab_size": len(kept_tokens),
            "embedding_dim": embedding_dim,
            "playable_ids": playable_ids,
            "total_pages": total_pages,
            "min_count": args.min_count,
            "max_vocab": args.max_vocab,
            "window_size": args.window_size,
            "explained_variance": float(svd.explained_variance_ratio_.sum()),
            "embed_chunks": embed_chunks,
            "token_unit": "lemma",
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Input shards: {len(input_paths)}")
    print(f"Pages counted: {total_pages}")
    print(f"Stopwords loaded: {len(stopwords)}")
    print(f"Lemma vocabulary size: {len(vocab_meta)}")
    print(f"Kept embedding rows: {len(kept_tokens)}")
    print(f"Variant aliases: {len(variants)}")
    print(f"Output: {output_dir}")
    print("Timing summary:")
    for label, elapsed in timings.items():
        print(f"- {label}: {format_seconds(elapsed)}")
    print(f"- total: {format_seconds(time.perf_counter() - total_start)}")


if __name__ == "__main__":
    main()
