from __future__ import annotations

import argparse
import bz2
from pathlib import Path

from .ja_constants import DEFAULT_ARCHIVE_NAME, DEFAULT_DATA_DIR, DEFAULT_XML_NAME
from .timing import byte_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decompress one or more Japanese Wikimedia bz2 dump shards."
    )
    parser.add_argument(
        "archive",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_ARCHIVE_NAME),
        help="Path to one compressed bz2 dump shard.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_XML_NAME),
        help="Output path for single-file extraction.",
    )
    parser.add_argument(
        "--all-pages-articles-shards",
        action="store_true",
        help="Extract every jawiki pages-articles shard found in the input directory.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory to scan when --all-pages-articles-shards is used.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory where extracted XML files should be written in batch mode.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip shards whose extracted XML already exists.",
    )
    return parser


def decompress_file(archive_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = archive_path.stat().st_size

    with (
        archive_path.open("rb") as raw_source,
        bz2.BZ2File(raw_source) as source,
        output_path.open("wb") as target,
    ):
        with byte_progress(
            total=total or None, title=f"Decompressing {archive_path.name}"
        ) as progress:
            processed = 0
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
                current = raw_source.tell()
                progress(current - processed)
                processed = current

    print(f"Wrote {output_path}")


def batch_archives(input_dir: Path) -> list[Path]:
    archives = sorted(input_dir.glob("jawiki-latest-pages-articles*.bz2"))
    if not archives:
        raise FileNotFoundError(f"No jawiki pages-articles shards found in {input_dir}")
    return archives


def main() -> None:
    args = build_parser().parse_args()

    if args.all_pages_articles_shards:
        input_dir = Path(args.input_dir).resolve()
        output_dir = Path(args.output_dir).resolve()
        for archive_path in batch_archives(input_dir):
            output_path = output_dir / archive_path.stem
            if args.skip_existing and output_path.exists():
                print(f"Skipping existing {output_path}")
                continue
            decompress_file(archive_path, output_path)
        return

    archive_path = Path(args.archive).resolve()
    output_path = Path(args.output).resolve()
    if args.skip_existing and output_path.exists():
        print(f"Skipping existing {output_path}")
        return
    decompress_file(archive_path, output_path)


if __name__ == "__main__":
    main()
