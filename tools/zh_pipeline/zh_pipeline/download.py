from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from .constants import (
    DEFAULT_ARCHIVE_NAME,
    DEFAULT_DATA_DIR,
    DEFAULT_DUMP_INDEX_URL,
    DEFAULT_DUMP_URL,
)
from .timing import byte_progress


PAGES_ARTICLES_PATTERN = re.compile(
    r'href="(zhwiki-latest-pages-articles\d+\.xml-p\d+p\d+\.bz2)"'
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a zh Wikipedia dump shard.")
    parser.add_argument("--url", default=DEFAULT_DUMP_URL, help="Dump URL to download.")
    parser.add_argument(
        "--all-pages-articles-shards",
        action="store_true",
        help="Download every zhwiki pages-articles shard listed in the dump index.",
    )
    parser.add_argument(
        "--index-url",
        default=DEFAULT_DUMP_INDEX_URL,
        help="Dump index page used to discover all pages-articles shards.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory where the compressed dump should be saved.",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_ARCHIVE_NAME,
        help="Name for the downloaded archive file.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already exist in the output directory.",
    )
    return parser


def discover_pages_articles_shards(index_url: str) -> list[str]:
    with urlopen(index_url) as response:
        html = response.read().decode("utf-8", errors="replace")

    shard_names = sorted(set(PAGES_ARTICLES_PATTERN.findall(html)))
    if not shard_names:
        raise RuntimeError(f"No pages-articles shard links found in {index_url}")
    return [urljoin(index_url, shard_name) for shard_name in shard_names]


def download_file(url: str, destination: Path) -> None:
    with urlopen(url) as response, destination.open("wb") as target:
        total = int(response.headers.get("Content-Length", "0"))
        with byte_progress(
            total=total or None,
            title=f"Downloading {destination.name}",
        ) as progress:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                written = target.write(chunk)
                progress(written)


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    urls = (
        discover_pages_articles_shards(args.index_url)
        if args.all_pages_articles_shards
        else [args.url]
    )

    for url in urls:
        destination = output_dir / Path(url).name
        if args.skip_existing and destination.exists():
            print(f"Skipping existing {destination}")
            continue
        download_file(url, destination)
        print(f"Downloaded {destination}")


if __name__ == "__main__":
    main()
