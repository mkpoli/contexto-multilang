from __future__ import annotations

import bz2
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import regex
import zstandard

from .clean_wikicode import strip_wiki_markup
from .xml_utils import iter_pages


WORDLIKE_PATTERN = regex.compile(
    r"[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Latin}\p{Nd}]"
)
KEEP_POS = {"名詞", "動詞", "形容詞", "形状詞", "副詞"}
TOKENIZER_STATE = threading.local()
DICTIONARY_BYTES: bytes | None = None

if TYPE_CHECKING:
    import vibrato


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
            "python-vibrato is required for Japanese tokenization. Install it with `pip install git+https://github.com/daac-tools/python-vibrato`."
        ) from exc
    return vibrato


def init_tokenizer(dictionary_path: Path) -> None:
    global DICTIONARY_BYTES
    vibrato = load_vibrato_module()
    DICTIONARY_BYTES = read_dictionary_bytes(dictionary_path)
    TOKENIZER_STATE.tokenizer = vibrato.Vibrato(DICTIONARY_BYTES)


def get_tokenizer() -> Any:
    tokenizer = getattr(TOKENIZER_STATE, "tokenizer", None)
    if tokenizer is None:
        if DICTIONARY_BYTES is None:
            raise RuntimeError(
                "Tokenizer not initialized. Call init_tokenizer() first."
            )
        vibrato = load_vibrato_module()
        tokenizer = vibrato.Vibrato(DICTIONARY_BYTES)
        TOKENIZER_STATE.tokenizer = tokenizer
    return tokenizer


def parse_feature_fields(feature: str) -> list[str]:
    return feature.split(",")


def extract_lemma(surface: str, feature: str) -> str | None:
    surface = surface.strip()
    if not surface or not WORDLIKE_PATTERN.search(surface):
        return None

    fields = parse_feature_fields(feature)
    pos = fields[0] if fields else ""
    if pos not in KEEP_POS:
        return None
    if pos.startswith("補助記号") or pos.startswith("記号"):
        return None

    for index in (10, 7, 8):
        if index < len(fields):
            candidate = fields[index].strip()
            if candidate and candidate != "*" and WORDLIKE_PATTERN.search(candidate):
                return candidate
    return surface


def tokenize_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for token in get_tokenizer().tokenize(text):
        surface = token.surface().strip()
        lemma = extract_lemma(surface, token.feature())
        if lemma is None:
            continue
        pairs.append((surface, lemma))
    return pairs


def tokenize_lemmas(text: str) -> list[str]:
    return [lemma for _, lemma in tokenize_pairs(text)]


def open_page_source(input_path: Path):
    if input_path.suffix == ".bz2":
        return bz2.BZ2File(input_path, "rb")
    return input_path.open("rb")


def iter_tokenized_pages(input_path: Path):
    with open_page_source(input_path) as source:
        for page in iter_pages(source):
            if page["namespace"] != "0" or page["redirect"]:
                continue
            title = page["title"]
            clean_text = strip_wiki_markup(page["text"], title=title)
            title_pairs = tokenize_pairs(title)
            text_pairs = tokenize_pairs(clean_text)
            if not title_pairs and not text_pairs:
                continue
            yield {
                "title_pairs": title_pairs,
                "text_pairs": text_pairs,
            }
