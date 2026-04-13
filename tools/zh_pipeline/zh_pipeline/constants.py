from __future__ import annotations

from pathlib import Path


DEFAULT_DUMP_INDEX_URL = "https://dumps.wikimedia.org/zhwiki/latest/"
DEFAULT_DUMP_URL = (
    DEFAULT_DUMP_INDEX_URL + "zhwiki-latest-pages-articles1.xml-p1p187712.bz2"
)
DEFAULT_DATA_DIR = Path("../../data/zh/wikimedia")
DEFAULT_ARCHIVE_NAME = "zhwiki-latest-pages-articles1.xml-p1p187712.bz2"
DEFAULT_XML_NAME = "zhwiki-latest-pages-articles1.xml-p1p187712"
DEFAULT_OUTPUT_NAME = "zhwiki-latest-pages-articles1.prototype-segmented.jsonl"
DEFAULT_SIMILARITY_NAME = "zhwiki-latest-pages-articles1.prototype-similarity.jsonl"
DEFAULT_STOPWORDS_DIR = DEFAULT_DATA_DIR / "stopwords"
DEFAULT_GAME_INDEX_DIR = Path("../../src/lib/generated/zh-game")
