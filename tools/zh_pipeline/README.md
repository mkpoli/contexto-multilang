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
- `uv run zh-download-stopwords`
- `uv run zh-inspect`
- `uv run zh-extract`
- `uv run zh-segment`
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
- Chinese and Ainu builders now keep all document frequencies by default; pass `--max-doc-ratio <value>` only if you intentionally want to exclude ultra-common terms

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

Japanese build note:

- the old Python Japanese pipeline has been removed
- build `ja-game` with the Rust tool in `tools/jawiki-lemma-counter`

Examples:

```sh
uv run inspect-game-vocab --game zh --top-freq 10 季節 歌曲
uv run inspect-game-vocab --game ja --top-freq 10 季節 --contains 音楽
uv run inspect-game-vocab --game ja --skip-top-freq --rank-samples 100,300,1000,3000,5000,10000,20000,30000,50000
```

Japanese full build:

- use `tools/jawiki-lemma-counter` for all Japanese analysis and build steps
- the Rust builder streams `.bz2` shards directly, indexes lemma forms, and preserves gameplay lookup through a surface-to-lemma variant map
- see `tools/jawiki-lemma-counter/README.md` for the current commands
