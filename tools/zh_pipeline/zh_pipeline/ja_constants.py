from __future__ import annotations

from pathlib import Path


DEFAULT_DUMP_INDEX_URL = "https://dumps.wikimedia.org/jawiki/latest/"
DEFAULT_DUMP_URL = (
    DEFAULT_DUMP_INDEX_URL + "jawiki-latest-pages-articles1.xml-p1p114794.bz2"
)
DEFAULT_DATA_DIR = Path("../../data/ja/wikimedia")
DEFAULT_ARCHIVE_NAME = "jawiki-latest-pages-articles1.xml-p1p114794.bz2"
DEFAULT_XML_NAME = "jawiki-latest-pages-articles1.xml-p1p114794"
DEFAULT_OUTPUT_NAME = "jawiki-latest-pages-articles1.prototype-segmented.jsonl"
DEFAULT_VIBRATO_DIR = DEFAULT_DATA_DIR / "vibrato"
DEFAULT_DICTIONARY_NAME = "system.dic.zst"
DEFAULT_DICTIONARY_PATH = DEFAULT_VIBRATO_DIR / DEFAULT_DICTIONARY_NAME
