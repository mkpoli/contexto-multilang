from __future__ import annotations

import argparse
from pathlib import Path

from .constants import DEFAULT_DATA_DIR, DEFAULT_XML_NAME
from .xml_utils import iter_pages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a decompressed Wikimedia XML dump shard."
    )
    parser.add_argument(
        "xml_path",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_XML_NAME),
        help="Path to the decompressed XML dump.",
    )
    parser.add_argument(
        "--sample-pages", type=int, default=5, help="How many sample pages to print."
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    xml_path = Path(args.xml_path).resolve()
    page_iter = iter_pages(xml_path)

    samples = []
    total_pages = 0
    main_namespace_pages = 0
    redirects = 0

    for page in page_iter:
        total_pages += 1
        if page["namespace"] == "0":
            main_namespace_pages += 1
        if page["redirect"]:
            redirects += 1
        if len(samples) < args.sample_pages:
            samples.append(page)
        if len(samples) >= args.sample_pages and total_pages >= 5000:
            break

    print(f"XML: {xml_path}")
    print(f"File size: {xml_path.stat().st_size} bytes")
    print(f"Pages scanned: {total_pages}")
    print(f"Namespace 0 pages in sample scan: {main_namespace_pages}")
    print(f"Redirects in sample scan: {redirects}")
    print("")
    print("Sample pages:")
    for page in samples:
        preview = page["text"].replace("\n", " ")[:100]
        print(f"- [{page['namespace']}] {page['title']} :: {preview}")


if __name__ == "__main__":
    main()
