## ain-vocab-pipeline

Python tooling to build `ain-game` artifacts from the Ainu JSONL corpus.

What it does:

- reads the local Ainu JSONL corpus
- tokenizes Ainu surface forms with affix splitting
- preserves normalized lookup aliases such as diacritic-stripped forms
- builds dense embeddings from cooccurrence windows
- writes `ain-game` artifacts compatible with the app runtime

Default paths:

- input corpus: `../../data/ain/ainu-corpora/data.jsonl`
- stopwords dir: `../../data/ain/stopwords`
- output dir: `../../src/lib/generated/ain-game`

Build game artifacts on the full corpus:

```sh
uv run ain-build-game-index
```

Build production-ready `ain-game` data from the repo root:

```sh
uv run --directory tools/ain-vocab-pipeline ain-build-game-index \
  data/ain/ainu-corpora/data.jsonl \
  src/lib/generated/ain-game \
  --stopwords-dir data/ain/stopwords \
  --min-count 3 \
  --max-doc-ratio 0.4 \
  --max-vocab 12000 \
  --window-size 4 \
  --embedding-dim 128 \
  --svd-iter 7
```

This command rebuilds the production `ain-game` artifacts in place for the app.

Build on a smaller sample:

```sh
uv run ain-build-game-index \
  ../../data/ain/ainu-corpora/data.jsonl \
  ../../src/lib/generated/ain-game-test \
  --limit-pages 2000 \
  --max-vocab 5000 \
  --embedding-dim 64
```

Outputs:

- `vocab.json`
- `variants.json`
- `metadata.json`
- `embeddings.f32.*.bin`

Inspect built artifacts with `tools/game-vocab-tools`:

```sh
cd ../game-vocab-tools
uv run game-vocab-stats --input-dir ../../src/lib/generated/ain-game
uv run game-vocab-neighbors --input-dir ../../src/lib/generated/ain-game h_ine hine
```

Notes:

- if `../../data/ain/stopwords` does not exist, the builder continues with no stopwords
- aliases include the original surface form plus a diacritic-stripped form when different
- underscores are removed during Ainu pipeline processing, so `hine` and `h_ine` are merged during build
- the frontend lookup also normalizes Ainu underscores, so runtime lookup matches the built data
