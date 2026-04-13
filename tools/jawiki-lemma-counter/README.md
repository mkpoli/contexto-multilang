## jawiki-lemma-counter

Rust tooling for Japanese Wikipedia lemma analysis and game-index building.

What it does:

- streams `jawiki` `.bz2` shards directly
- tokenizes with `vibrato`
- extracts lemma forms for content-heavy parts of speech
- applies local Japanese stopword lists
- supports a fast frequency/cutoff analysis mode
- can build `ja-game` artifacts compatible with the app runtime

Analyze cutoff candidates:

```sh
cargo run --release -- \
  ../../data/ja/wikimedia/jawiki-latest-pages-articles1.xml-p1p114794.bz2 \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --limit-pages 2000 \
  --top-freq 40 \
  --sample-ranks 100,300,1000,3000,5000,10000,20000
```

Analyze all downloaded shards:

```sh
cargo run --release -- \
  --all-pages-articles-shards \
  --input-dir ../../data/ja/wikimedia \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --sample-ranks 100,300,1000,3000,5000,10000,20000,30000
```

Build game artifacts on a small sample:

```sh
cargo run --release -- \
  ../../data/ja/wikimedia/jawiki-latest-pages-articles1.xml-p1p114794.bz2 \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --limit-pages 200 \
  --max-vocab 5000 \
  --embedding-dim 64 \
  --build-output-dir ../../src/lib/generated/ja-game-rust-test
```

Build game artifacts from all downloaded shards:

```sh
cargo run --release -- \
  --all-pages-articles-shards \
  --input-dir ../../data/ja/wikimedia \
  --dictionary ../../data/ja/wikimedia/vibrato/system.dic.zst \
  --stopwords-dir ../../data/ja/wikimedia/stopwords \
  --min-count 10 \
  --max-vocab 20000 \
  --embedding-dim 256 \
  --build-output-dir ../../src/lib/generated/ja-game
```

Outputs in build mode:

- `vocab.json`
- `variants.json`
- `metadata.json`
- `embeddings.f32.*.bin`

Notes:

- the progress bar is based on compressed bytes read, so it stays bounded during concurrent counting
- counting is parallelized by shard
- cooccurrence/build is currently single-process inside the Rust tool
- the wiki cleaner is lighter than the Python `mwparserfromhell` path, so inspect the resulting vocab before replacing the production dataset
