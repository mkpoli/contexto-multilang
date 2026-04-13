from __future__ import annotations

from html import unescape

import mwparserfromhell
import regex


COMMENT_PATTERN = regex.compile(r"<!--.*?-->", regex.DOTALL)
MAGIC_WORD_PATTERN = regex.compile(r"__[^_\s]+__")
STYLE_MARKER_PATTERN = regex.compile(r"'{2,}")
NAMESPACED_LINK_PATTERN = regex.compile(
    r"\[\[\s*:?\s*(?:Category|File|Help|Image|Module|Portal|Special|Template|TimedText|Wikipedia|"
    r"文件|档案|檔案|分类|分類|帮助|幫助|模板|维基百科|維基百科)\s*:[^\]]+\]\]"
)
URL_PATTERN = regex.compile(r"https?://\S+")
TABLE_PATTERN = regex.compile(r"\{\|.*?\|\}", regex.DOTALL)
BRACKET_RESIDUE_PATTERN = regex.compile(r"[\[\]]{2,}")
PAREN_EMPTY_PATTERN = regex.compile(r"[（(]\s*[)）]")
HTML_ENTITY_PAREN_PATTERN = regex.compile(r"[（(]\s*[A-Za-z0-9 ,;:/._'\"-]*\s*[)）]")
LATIN_PAREN_PATTERN = regex.compile(r"[（(][^()（）]*[A-Za-z][^()（）]*[)）]")
LATIN_CHUNK_PATTERN = regex.compile(r"\b[\p{Latin}][\p{Latin}\p{N} .,:;/'\"_\-]{2,}\b")
HEADING_EQUALS_PATTERN = regex.compile(r"={2,}\s*([^=]+?)\s*={2,}")
LIST_MARKER_PATTERN = regex.compile(r"(?:^|\s)[*#;:]+(?=\s)")
HTML_TAG_PATTERN = regex.compile(r"</?[A-Za-z][^>]*>")
NON_TEXT_SYMBOL_PATTERN = regex.compile(r"[|<>`~_^]+")
MULTI_PUNCT_PATTERN = regex.compile(r"\s*([，。！？；：、])\s*")
LEADING_JUNK_PATTERN = regex.compile(r"^[，。；：、】【\-\s]+")
SPACE_PATTERN = regex.compile(r"\s+")

DROP_TAGS = {
    "categorytree",
    "charinsert",
    "gallery",
    "graph",
    "imagemap",
    "indicator",
    "math",
    "nowiki",
    "pre",
    "ref",
    "references",
    "score",
    "syntaxhighlight",
    "templatedata",
    "timeline",
}


def trim_leading_non_article_text(text: str, title: str) -> str:
    if not text or not title:
        return text

    anchor = text.find(title)
    if 0 < anchor <= 200:
        return text[anchor:]
    return text


def strip_wiki_markup(text: str, title: str = "") -> str:
    if not text:
        return ""

    text = unescape(text)
    text = COMMENT_PATTERN.sub(" ", text)
    text = TABLE_PATTERN.sub(" ", text)
    text = MAGIC_WORD_PATTERN.sub(" ", text)
    text = NAMESPACED_LINK_PATTERN.sub(" ", text)

    for tag_name in DROP_TAGS:
        text = regex.sub(
            rf"<{tag_name}\b[^>/]*?/>",
            " ",
            text,
            flags=regex.IGNORECASE | regex.DOTALL,
        )
        text = regex.sub(
            rf"<{tag_name}\b[^>]*?>.*?</{tag_name}>",
            " ",
            text,
            flags=regex.IGNORECASE | regex.DOTALL,
        )

    code = mwparserfromhell.parse(text, skip_style_tags=True)

    cleaned = code.strip_code(normalize=True, collapse=True)
    cleaned = unescape(cleaned)
    cleaned = HEADING_EQUALS_PATTERN.sub(r" \1 ", cleaned)
    cleaned = LIST_MARKER_PATTERN.sub(" ", cleaned)
    cleaned = HTML_TAG_PATTERN.sub(" ", cleaned)
    cleaned = STYLE_MARKER_PATTERN.sub(" ", cleaned)
    cleaned = BRACKET_RESIDUE_PATTERN.sub(" ", cleaned)
    cleaned = PAREN_EMPTY_PATTERN.sub(" ", cleaned)
    cleaned = HTML_ENTITY_PAREN_PATTERN.sub(" ", cleaned)
    cleaned = LATIN_PAREN_PATTERN.sub(" ", cleaned)
    cleaned = LATIN_CHUNK_PATTERN.sub(" ", cleaned)
    cleaned = URL_PATTERN.sub(" ", cleaned)
    cleaned = NON_TEXT_SYMBOL_PATTERN.sub(" ", cleaned)
    cleaned = MULTI_PUNCT_PATTERN.sub(r"\1", cleaned)
    cleaned = SPACE_PATTERN.sub(" ", cleaned)
    cleaned = trim_leading_non_article_text(cleaned.strip(), title)
    cleaned = LEADING_JUNK_PATTERN.sub("", cleaned)
    return cleaned.strip()
