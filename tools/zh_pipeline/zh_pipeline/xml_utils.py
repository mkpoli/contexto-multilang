from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


MEDIAWIKI_NS = "{http://www.mediawiki.org/xml/export-0.11/}"


def child_text(node: ET.Element, tag: str) -> str:
    child = node.find(f"{MEDIAWIKI_NS}{tag}")
    return child.text if child is not None and child.text is not None else ""


def iter_pages(xml_path: Path):
    context = ET.iterparse(xml_path, events=("end",))
    for _, element in context:
        if element.tag != f"{MEDIAWIKI_NS}page":
            continue

        revision = element.find(f"{MEDIAWIKI_NS}revision")
        text_node = (
            revision.find(f"{MEDIAWIKI_NS}text") if revision is not None else None
        )

        page = {
            "id": child_text(element, "id"),
            "title": child_text(element, "title"),
            "namespace": child_text(element, "ns"),
            "redirect": element.find(f"{MEDIAWIKI_NS}redirect") is not None,
            "text": text_node.text
            if text_node is not None and text_node.text is not None
            else "",
        }

        yield page
        element.clear()
