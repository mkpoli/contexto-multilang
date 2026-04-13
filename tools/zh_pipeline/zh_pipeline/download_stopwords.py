from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from .constants import DEFAULT_STOPWORDS_DIR


STOPWORD_URLS = {
    "cn_stopwords.txt": "https://raw.githubusercontent.com/goto456/stopwords/master/cn_stopwords.txt",
    "hit_stopwords.txt": "https://raw.githubusercontent.com/goto456/stopwords/master/hit_stopwords.txt",
    "baidu_stopwords.txt": "https://raw.githubusercontent.com/goto456/stopwords/master/baidu_stopwords.txt",
    "scu_stopwords.txt": "https://raw.githubusercontent.com/goto456/stopwords/master/scu_stopwords.txt",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Chinese stopword lists used by the similarity pipeline."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=str(DEFAULT_STOPWORDS_DIR),
        help="Directory where stopword files should be stored.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in STOPWORD_URLS.items():
        output_path = output_dir / filename
        urllib.request.urlretrieve(url, output_path)
        print(f"Downloaded {filename} -> {output_path}")


if __name__ == "__main__":
    main()
