from __future__ import annotations

import json
from pathlib import Path

import numpy as np


DEFAULT_ROOT = Path("../../src/lib/generated")


def resolve_input_dir(game: str, input_dir: str | None) -> Path:
    if input_dir:
        return Path(input_dir).resolve()
    return (DEFAULT_ROOT / f"{game}-game").resolve()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_vocab_bundle(input_dir: Path) -> tuple[dict, list[dict]]:
    metadata = load_json(input_dir / "metadata.json")
    vocab = load_json(input_dir / "vocab.json")
    return metadata, vocab


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


def ordered_vocab(vocab: list[dict]) -> list[dict]:
    return sorted(
        vocab,
        key=lambda row: (-row["count"], -row["doc_frequency"], row["word"]),
    )


def parse_rank_values(raw: str | None) -> list[int]:
    if not raw:
        return []
    values = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
    return [value for value in values if value > 0]


def resolve_query_ids(
    word: str, word_to_id: dict[str, int], variants: dict[str, list[int]]
) -> list[int]:
    variant_ids = variants.get(word)
    if variant_ids:
        return variant_ids
    exact_id = word_to_id.get(word)
    return [] if exact_id is None else [exact_id]
