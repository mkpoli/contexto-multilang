from __future__ import annotations

import argparse
import bz2
from pathlib import Path

from .ja_constants import DEFAULT_ARCHIVE_NAME, DEFAULT_DATA_DIR, DEFAULT_XML_NAME
from .timing import byte_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decompress a Japanese Wikimedia bz2 dump shard."
    )
    parser.add_argument(
        "archive",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_ARCHIVE_NAME),
        help="Path to the compressed bz2 dump.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(DEFAULT_DATA_DIR / DEFAULT_XML_NAME),
        help="Path where the decompressed XML should be written.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    archive_path = Path(args.archive).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = archive_path.stat().st_size

    with (
        archive_path.open("rb") as raw_source,
        bz2.BZ2File(raw_source) as source,
        output_path.open("wb") as target,
    ):
        with byte_progress(total=total or None, title="Decompressing") as progress:
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


if __name__ == "__main__":
    main()
