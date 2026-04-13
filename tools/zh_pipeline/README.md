## zh-pipeline

Utilities for preparing a Chinese Wikipedia corpus for word-similarity experiments.

This prototype uses the first split file from the Wikimedia `zhwiki` pages-articles dump:

- `zhwiki-latest-pages-articles1.xml-p1p187712.bz2`

The pipeline now does three main things:

- strip MediaWiki markup from article text
- segment Chinese text into words with `pynlpir`/NLPIR
- build dense word embeddings and exact game-time ranking data from word co-occurrence windows

Markup-cleaning approach:

- parse wikitext with `mwparserfromhell`
- drop templates instead of trying to expand them inside the XML dump
- remove noisy tags like `ref`, `math`, `gallery`, `nowiki`, and `syntaxhighlight`
- discard file/category/template-style links
- collapse the remaining plain text before Han extraction

Why this approach:

- MediaWiki template expansion is complex and recursive; raw XML dumps do not contain already-rendered article text
- common best practice is to use a proper wiki parser or an extractor such as WikiExtractor rather than regex-only cleanup
- for this prototype, `mwparserfromhell` gives a lightweight middle ground without pulling in a full dump extractor pipeline

Available commands:

- `uv run zh-download`
- `uv run ja-download`
- `uv run zh-download-stopwords`
- `uv run zh-inspect`
- `uv run zh-extract`
- `uv run ja-extract`
- `uv run zh-segment`
- `uv run ja-segment --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst`
- `uv run ja-build-game-index --all-pages-articles-shards ../../src/lib/generated/ja-game`
- `uv run ja-analyze-vocab --all-pages-articles-shards`
- `uv run zh-build-similarity`
- `uv run zh-build-game-index`
- `uv run zh-eval-neighbors -- <word> [more_words...]`
- `uv run inspect-game-vocab --game zh <word> [more_words...]`

Outputs:

- segmented pages JSONL: one article per line with `title_tokens` and `text_tokens`
- similarity JSONL: one word per line with its nearest semantic neighbors and scores
- game index artifacts:
  - `src/lib/generated/zh-game/vocab.json`
  - `src/lib/generated/zh-game/metadata.json`
  - `src/lib/generated/zh-game/embeddings.f32.bin`

Suggested workflow:

```sh
uv run zh-download
uv run zh-download-stopwords
uv run zh-extract
uv run zh-inspect --sample-pages 5
uv run zh-segment --limit-pages 5000
uv run zh-build-similarity --limit-pages 5000 --min-count 20 --top-k 200 --chunk-size 128
uv run zh-build-game-index --limit-pages 5000 --min-count 10 --max-vocab 5000 --embedding-dim 256
uv run zh-eval-neighbors -- 数学 哲学
```

Fast rebuild loop:

```sh
uv run zh-build-similarity \
  ../../data/zh/wikimedia/zhwiki-latest-pages-articles1.prototype-segmented.jsonl \
  ../../data/zh/wikimedia/zhwiki-latest-pages-articles1.prototype-similarity.jsonl \
  --limit-pages 5000 --min-count 10 --top-k 50 --chunk-size 128
```

- `zh-segment` only needs to run again if the XML dump or cleaning/segmentation logic changed
- `zh-segment` now uses `pynlpir` and automatically bootstraps the NLPIR license into the local venv on first run
- full segmentation runs use a threaded batch pipeline via `--workers` and `--batch-size` to favor wall-clock speed
- `--limit-pages` uses a sequential path so the prototype loop can stop exactly on the requested article count
- all long-running pipeline commands now use `alive-progress` for progress display
- `zh-build-similarity` now uses chunked sparse cosine scoring, so reruns can reuse the segmented JSONL directly
- `zh-build-game-index` also reuses the segmented JSONL and produces the artifacts used by the frontend/backend gameplay path
- the builders use integer-indexed cooccurrence rows internally to reduce Python string/hash overhead
- both builders now print per-step timing summaries so you can see where build time is going

Game-serving approach:

- the frontend no longer relies on sparse top-k neighbors for guess validation
- instead, the backend loads one embedding per word and builds an exact rank cache the first time an answer is used
- this accepts almost any in-corpus guess, while keeping stored artifacts compact
- top neighbors are still useful for reveal UI and evaluator sanity checks

Stopwords:

- stopwords are downloaded from `goto456/stopwords`
- the builder merges `cn`, `hit`, `baidu`, and `scu` lists from the local cache directory
- if the files are missing, `zh-build-similarity` will fail fast and tell you to run `zh-download-stopwords`

Notes on the similarity output:

- this is row-wise sparse output, not a fully materialized dense NxN matrix
- that keeps storage practical while still matching the game's lookup needs
- each row contains one word and its top semantic neighbors, which is what the game actually queries

Evaluator:

- `zh-eval-neighbors` is a quick sanity-check tool for the similarity output
- it prints nearest neighbors for one or more sample words from the JSONL rows
- add `--contains` to also show substring matches when an exact row is missing
- `inspect-game-vocab` inspects the generated game artifacts used by the frontend/backend gameplay path
- it prints corpus stats, the most frequent words, and nearest neighbors from the stored dense embeddings
- it can also print rank cutoff summaries from the already-built vocab with `--rank-samples`, which is the fastest way to judge `max-vocab` after one build
- use `--game zh` or `--game ja`, or pass a custom artifact directory with `--input-dir`

Examples:

```sh
uv run inspect-game-vocab --game zh --top-freq 10 季節 歌曲
uv run inspect-game-vocab --game ja --top-freq 10 季節 --contains 音楽
uv run inspect-game-vocab --game ja --skip-top-freq --rank-samples 100,300,1000,3000,5000,10000,20000,30000,50000
```

Japanese full build:

- `ja-download` mirrors the Chinese dump downloader, but defaults to `jawiki`
- `ja-extract` can still decompress one shard or all downloaded shards, but it is optional for Japanese game building
- `ja-segment` is now mainly a debugging/prototyping tool; the preferred production path is `ja-build-game-index`
- `ja-analyze-vocab` runs only the counting pass and prints the frequency curve at chosen rank cutoffs, which is useful for selecting `--max-vocab`
- `ja-build-game-index` streams XML or `.bz2` shards directly, lemmatizes with Vibrato, filters to content-heavy parts of speech, and builds the final game artifacts without an intermediate segmented corpus
- the Japanese builder indexes lemma forms, not surface forms, and preserves gameplay matching through a generated surface-to-lemma variant map
- install `python-vibrato` separately before running Japanese tools: `pip install git+https://github.com/daac-tools/python-vibrato`
- `python-vibrato` does not ship a dictionary, so download a compatible Vibrato dictionary first, for example `ipadic-mecab-2_7_0/system.dic.zst` from the Vibrato releases page
- default dictionary location is `../../data/ja/wikimedia/vibrato/system.dic.zst`
- on this machine, `python-vibrato` segfaults under Python 3.14 but works under Python 3.11; use the Python 3.11 venv for Japanese builds
- if your existing Python 3.11 venv was created before `ja-build-game-index` was added, call it as `python -m zh_pipeline.ja_build_game_index` instead of relying on the console script

Preferred full build for the Japanese game:

```sh
cd tools/zh_pipeline

# 1. Download all jawiki pages-articles shards
uv run ja-download --all-pages-articles-shards --skip-existing

# 2. Ensure the Vibrato dictionary is available
mkdir -p ../../data/ja/wikimedia/vibrato
# Place system.dic.zst at:
# ../../data/ja/wikimedia/vibrato/system.dic.zst

# 3. Put Japanese stopword txt files in ../../data/ja/wikimedia/stopwords

# 4. Build the final ja-game artifacts directly from the bz2 shards
./.venv311p/bin/python -m zh_pipeline.ja_build_game_index \
  --all-pages-articles-shards \
  --input-dir ../../data/ja/wikimedia \
  ../../src/lib/generated/ja-game \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --min-count 10 \
  --max-vocab 50000 \
  --embedding-dim 256
```

Quick test build on a small sample:

```sh
cd tools/zh_pipeline
./.venv311p/bin/python -m zh_pipeline.ja_build_game_index \
  ../../data/ja/wikimedia/jawiki-latest-pages-articles1.xml-p1p114794.bz2 \
  ../../src/lib/generated/ja-game-test \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --limit-pages 2000 \
  --min-count 10 \
  --max-vocab 12000 \
  --embedding-dim 256
```

Investigate where to stop the vocabulary:

```sh
cd tools/zh_pipeline
./.venv311p/bin/python -m zh_pipeline.ja_analyze_vocab \
  --all-pages-articles-shards \
  --input-dir ../../data/ja/wikimedia \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --min-count 1 \
  --sample-ranks 100,300,1000,3000,5000,10000,20000,30000,50000,70000,100000
```

- this prints the lemma and count at each requested rank
- the count at rank `N` is a practical way to judge whether `--max-vocab N` is still keeping meaningful words or already entering the noisy tail

Operational notes for the full run:

- the latest `jawiki` dump is split across several large shard files, totaling multiple gigabytes compressed
- direct `ja-build-game-index` from `.bz2` is even more disk-efficient because it also avoids storing a large segmented JSONL
- you can safely rerun the download step with `--skip-existing`
- if you do extract XML for debugging, remove it after segmentation to recover space
- the current Japanese builder indexes lemmas, not surface forms, and keeps a surface-to-lemma alias map for gameplay lookups
