from __future__ import annotations

import argparse
import json
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import regex
from sklearn.decomposition import TruncatedSVD

from .build_game_index import normalize_embeddings
from .build_similarity import build_vocab, load_stopwords
from .timing import format_seconds, iter_progress, timed_step


TOKEN_PATTERN = regex.compile(r"\s+|([\p{L}=]+)|(\p{P})", regex.UNICODE)
WORD_PATTERN = regex.compile(r"^[\p{L}=]+$", regex.UNICODE)
AINU_WORD_PATTERN = regex.compile(r"^[a-zA-Zâîûêôáíúéó=\-_'’\[\]]+$")
APOSTROPHE_SPLIT_PATTERN = regex.compile(r"^(['’‘])?([^'’‘]*)(['’‘])?$")
PREFIXES = [
    "ku",
    "k",
    "en",
    "in",
    "ci",
    "c",
    "un",
    "a",
    "i",
    "an",
    "e",
    "eci",
    "ec",
]
SUFFIXES = ["an", "as"]
PREFIX_GROUP = rf"((?:{'|'.join(PREFIXES)})=)?"
SUFFIX_GROUP = rf"(=(?:{'|'.join(SUFFIXES)}))?"
AFFIX_PATTERN = regex.compile(rf"{PREFIX_GROUP}{PREFIX_GROUP}([a-z/-]+){SUFFIX_GROUP}")
WORD_SPLIT_PATTERN = regex.compile(
    r"((?:\.\.\.(\.\.\.)?)|[a-zA-Zâîûêôáíúéó=\-_'’\[\]]+|\d+|[<>\.,‘\"“”])|\s+"
)
LETTER_PATTERN = regex.compile(r"[a-zA-Zâîûêôáíúéó]")
DEFAULT_INPUT_PATH = Path("../../data/ain/ainu-corpora/data.jsonl")
DEFAULT_STOPWORDS_DIR = Path("../../data/ain/stopwords")
DEFAULT_GAME_INDEX_DIR = Path("../../src/lib/generated/ain-game")
MAX_EMBED_CHUNK_BYTES = 25 * 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dense Ainu word embeddings from the Ainu JSONL corpus."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(DEFAULT_INPUT_PATH),
        help="Path to the Ainu JSONL corpus.",
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
        help="Directory containing Ainu stopword txt files.",
    )
    parser.add_argument("--limit-pages", type=int, default=None)
    parser.add_argument("--min-count", type=int, default=3)
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-doc-ratio", type=float, default=1.0)
    parser.add_argument("--max-vocab", type=int, default=12000)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--embedding-dim", type=int, default=128)
    parser.add_argument("--svd-iter", type=int, default=7)
    return parser


def load_optional_stopwords(stopwords_dir: Path) -> set[str]:
    if not stopwords_dir.exists():
        return set()
    try:
        return load_stopwords(stopwords_dir)
    except FileNotFoundError:
        return set()


def split_affixes(word: str) -> list[str]:
    if word.count("=") + word.count("-") >= 2:
        parts = AFFIX_PATTERN.match(word)
        if not parts:
            return [word]
        return [part for part in parts.groups() if part]

    parts = regex.split(r"([-=])", word)
    if len(parts) == 1:
        return [word]
    try:
        a, sep, b = parts
    except ValueError:
        return [word]
    if len(a) > len(b):
        return [a, sep + b]
    return [a + sep, b]


def split_affixing_apostrophes(word: str) -> list[str]:
    if len(word) < 2:
        return [word]
    match = APOSTROPHE_SPLIT_PATTERN.match(word)
    if not match:
        return [word]
    prefix, middle, suffix = match.groups()
    if prefix and suffix:
        return [prefix, middle, suffix]
    if prefix:
        return [prefix, middle]
    if suffix:
        return [middle, suffix]
    return [word]


def is_word(word: str) -> bool:
    return bool(AINU_WORD_PATTERN.match(word)) and bool(LETTER_PATTERN.search(word))


def split_sentence_words(input_text: str) -> list[str]:
    return [
        part
        for part in WORD_SPLIT_PATTERN.split(input_text)
        if part and not part.isspace()
    ]


def tokenize(input_text: str) -> list[str]:
    words = split_sentence_words(input_text)
    words = [piece for word in words for piece in split_affixing_apostrophes(word)]
    words = [piece for word in words for piece in split_affixes(word)]
    return [word.lower() for word in words if word and is_word(word)]


def token_alias_groups(input_text: str) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    for raw_word in split_sentence_words(input_text):
        lowered = raw_word.lower()
        parts = [
            piece
            for word in split_affixing_apostrophes(lowered)
            for piece in split_affixes(word)
        ]
        parts = [part for part in parts if part and is_word(part)]
        if not parts:
            continue
        groups.append((lowered, parts))
        stripped = strip_diacritics(lowered)
        if stripped != lowered:
            groups.append((stripped, parts))
    return groups


def strip_diacritics(token: str) -> str:
    normalized = unicodedata.normalize("NFKD", token)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return unicodedata.normalize("NFC", stripped)


def iter_records(input_path: Path):
    with input_path.open("r", encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = (record.get("text") or "").strip()
            if not text:
                continue
            yield record


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
    for record in iter_progress(
        iter_records(input_path),
        total=limit_pages,
        title="Counting Ainu vocabulary",
    ):
        if limit_pages is not None and total_pages >= limit_pages:
            break
        tokens = [
            token
            for token in tokenize(record["text"])
            if len(token) >= min_length and token not in stopwords
        ]
        if not tokens:
            continue
        total_pages += 1
        term_frequency.update(tokens)
        document_frequency.update(set(tokens))
    return term_frequency, document_frequency, total_pages


def build_cooccurrence(
    input_path: Path,
    *,
    vocab_tokens: list[str],
    limit_pages: int | None,
    min_length: int,
    stopwords: set[str],
    window_size: int,
    counts: list[int],
    doc_frequencies: list[int],
):
    token_to_index = {token: index for index, token in enumerate(vocab_tokens)}
    vectors = [Counter() for _ in vocab_tokens]
    variants: dict[str, set[int]] = defaultdict(set)
    processed_pages = 0

    for record in iter_progress(
        iter_records(input_path),
        total=limit_pages,
        title="Building Ainu cooccurrence",
    ):
        if limit_pages is not None and processed_pages >= limit_pages:
            break
        text = record["text"]
        tokens = [
            token
            for token in tokenize(text)
            if len(token) >= min_length and token not in stopwords
        ]
        alias_groups = token_alias_groups(text)
        token_ids: list[int] = []
        for token in tokens:
            token_id = token_to_index.get(token)
            if token_id is None:
                continue
            variants[token].add(token_id)
            variants[strip_diacritics(token)].add(token_id)
            token_ids.append(token_id)
        for alias, parts in alias_groups:
            alias_ids = [
                token_to_index[token]
                for token in parts
                if len(token) >= min_length
                and token not in stopwords
                and token in token_to_index
            ]
            for token_id in alias_ids:
                variants[alias].add(token_id)
        if not token_ids:
            continue

        processed_pages += 1
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
    finalized_variants = {
        alias: sorted(token_ids, key=lambda token_id: rank[token_id])
        for alias, token_ids in variants.items()
        if alias.strip()
    }
    return vectors, finalized_variants


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
        if len(word) > 20:
            continue
        if count < 5 or doc_frequency < 2:
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
    input_path = Path(args.input_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    stopwords_dir = Path(args.stopwords_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with timed_step("load stopwords", timings):
        stopwords = load_optional_stopwords(stopwords_dir)
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
    counts = [vocab_meta[word]["count"] for word in vocab_tokens]
    doc_frequencies = [vocab_meta[word]["doc_frequency"] for word in vocab_tokens]
    with timed_step("build cooccurrence", timings):
        vectors, variants = build_cooccurrence(
            input_path,
            vocab_tokens=vocab_tokens,
            limit_pages=args.limit_pages,
            min_length=args.min_length,
            stopwords=stopwords,
            window_size=args.window_size,
            counts=counts,
            doc_frequencies=doc_frequencies,
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
            "token_unit": "surface",
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Pages counted: {total_pages}")
    print(f"Stopwords loaded: {len(stopwords)}")
    print(f"Ainu vocabulary size: {len(vocab_meta)}")
    print(f"Kept embedding rows: {len(kept_tokens)}")
    print(f"Variant aliases: {len(variants)}")
    print(f"Output: {output_dir}")
    print("Timing summary:")
    for label, elapsed in timings.items():
        print(f"- {label}: {format_seconds(elapsed)}")
    print(f"- total: {format_seconds(time.perf_counter() - total_start)}")


if __name__ == "__main__":
    main()
