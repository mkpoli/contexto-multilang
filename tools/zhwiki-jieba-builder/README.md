## zhwiki-jieba-builder

Rust tooling for Chinese Wikipedia word analysis and game-index building using `jieba-rs`.

What it does:

- streams `zhwiki` `.bz2` shards directly
- tokenizes Chinese text with `jieba-rs`
- applies local Chinese stopword lists
- supports a fast frequency/cutoff analysis mode
- can build `zh-game` artifacts compatible with the app runtime

Analyze cutoff candidates:

```sh
cargo run --release -- \
  ../../data/zh/wikimedia/zhwiki-latest-pages-articles1.xml-p1p187712.bz2 \
  --stopwords-dir ../../data/zh/wikimedia/stopwords \
  --limit-pages 2000 \
  --top-freq 40 \
  --sample-ranks 100,300,1000,3000,5000,10000,20000
```

Build game artifacts on a small sample:

```sh
cargo run --release -- \
  ../../data/zh/wikimedia/zhwiki-latest-pages-articles1.xml-p1p187712.bz2 \
  --stopwords-dir ../../data/zh/wikimedia/stopwords \
  --limit-pages 200 \
  --max-vocab 5000 \
  --embedding-dim 64 \
  --build-output-dir ../../src/lib/generated/zh-game-rust-test
```

Build game artifacts from all downloaded shards:

```sh
cargo run --release -- \
  --all-pages-articles-shards \
  --input-dir ../../data/zh/wikimedia \
  --stopwords-dir ../../data/zh/wikimedia/stopwords \
  --min-count 10 \
  --max-vocab 20000 \
  --embedding-dim 256 \
  --build-output-dir ../../src/lib/generated/zh-game
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
- the Chinese cleaner is lighter than the Python `mwparserfromhell` path, so inspect the resulting vocab before replacing the production dataset
