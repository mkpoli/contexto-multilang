from __future__ import annotations

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any

import regex
import zstandard

from .clean_wikicode import strip_wiki_markup
from .ja_constants import (
    DEFAULT_DATA_DIR,
    DEFAULT_DICTIONARY_PATH,
    DEFAULT_OUTPUT_NAME,
    DEFAULT_XML_NAME,
)
from .timing import iter_progress
from .xml_utils import iter_pages


WORDLIKE_PATTERN = regex.compile(
    r"[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Latin}\p{Nd}]"
)
TOKENIZER_STATE = threading.local()
DICTIONARY_BYTES: bytes | None = None

if TYPE_CHECKING:
    import vibrato


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Segment Japanese words from a Wikimedia XML dump shard."
    )
    parser.add_argument(
        "xml_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_XML_NAME),
        help="Path to the decompressed XML dump.",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_OUTPUT_NAME),
        help="Path to the JSONL output file.",
    )
    parser.add_argument(
        "--dictionary",
        default=str(DEFAULT_DICTIONARY_PATH),
        help="Path to a Vibrato system dictionary (.dic or .dic.zst).",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Optional limit for processed namespace-0 pages.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Number of worker threads for cleanup and segmentation.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Pages per worker batch. Larger batches reduce IPC overhead.",
    )
    return parser


def read_dictionary_bytes(dictionary_path: Path) -> bytes:
    with dictionary_path.open("rb") as source:
        if dictionary_path.suffix == ".zst":
            decompressor = zstandard.ZstdDecompressor()
            with decompressor.stream_reader(source) as reader:
                return reader.read()
        return source.read()


def load_vibrato_module() -> Any:
    try:
        import vibrato
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "python-vibrato is required for ja-segment. Install it with `pip install git+https://github.com/daac-tools/python-vibrato`."
        ) from exc
    return vibrato


def init_segmenter(dictionary_path: Path) -> None:
    global DICTIONARY_BYTES
    vibrato = load_vibrato_module()
    DICTIONARY_BYTES = read_dictionary_bytes(dictionary_path)
    TOKENIZER_STATE.tokenizer = vibrato.Vibrato(DICTIONARY_BYTES)


def get_tokenizer() -> Any:
    tokenizer = getattr(TOKENIZER_STATE, "tokenizer", None)
    if tokenizer is None:
        if DICTIONARY_BYTES is None:
            raise RuntimeError(
                "Tokenizer not initialized. Call init_segmenter() first."
            )
        vibrato = load_vibrato_module()
        tokenizer = vibrato.Vibrato(DICTIONARY_BYTES)
        TOKENIZER_STATE.tokenizer = tokenizer
    return tokenizer


def should_keep_token(surface: str, feature: str) -> bool:
    if not surface or not WORDLIKE_PATTERN.search(surface):
        return False
    if feature.startswith("記号,"):
        return False
    return True


def segment_words(text: str) -> list[str]:
    return [
        surface
        for token in get_tokenizer().tokenize(text)
        if should_keep_token(
            surface := token.surface().strip(),
            feature=token.feature(),
        )
    ]


def process_page(page: dict[str, str | bool]) -> dict[str, object] | None:
    if page["namespace"] != "0" or page["redirect"]:
        return None

    title = page["title"]
    clean_text = strip_wiki_markup(page["text"], title=title)
    title_tokens = segment_words(title)
    text_tokens = segment_words(clean_text)

    if not title_tokens and not text_tokens:
        return None

    return {
        "id": page["id"],
        "title": title,
        "title_tokens": title_tokens,
        "clean_text": clean_text,
        "text_tokens": text_tokens,
        "token_count": len(text_tokens),
    }


def process_page_batch(pages: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for page in pages:
        record = process_page(page)
        if record is not None:
            records.append(record)
    return records


def iter_batches(xml_path: Path, batch_size: int):
    page_iter = iter_pages(xml_path)
    while True:
        batch = list(islice(page_iter, batch_size))
        if not batch:
            break
        yield batch


def write_record(target, record: dict[str, object]) -> None:
    target.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    args = build_parser().parse_args()
    xml_path = Path(args.xml_path).resolve()
    output_path = Path(args.output_path).resolve()
    dictionary_path = Path(args.dictionary).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    init_segmenter(dictionary_path)

    processed_pages = 0

    with output_path.open("w", encoding="utf-8") as target:
        if args.limit_pages is not None or args.workers <= 1:
            for page in iter_progress(
                iter_pages(xml_path),
                total=None,
                title="Segmenting pages",
            ):
                record = process_page(page)
                if record is None:
                    continue
                write_record(target, record)
                processed_pages += 1
                if args.limit_pages is not None and processed_pages >= args.limit_pages:
                    print(f"Wrote {processed_pages} tokenized pages to {output_path}")
                    return
        else:
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                batch_iter = pool.map(
                    process_page_batch,
                    iter_batches(xml_path, max(1, args.batch_size)),
                    chunksize=1,
                )
                for batch_records in iter_progress(
                    batch_iter,
                    total=None,
                    title="Segmenting batches",
                ):
                    for record in batch_records:
                        write_record(target, record)
                        processed_pages += 1

    print(f"Wrote {processed_pages} tokenized pages to {output_path}")


if __name__ == "__main__":
    main()
