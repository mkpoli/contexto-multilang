## ko-vocab-pipeline

Rust tooling for the end-to-end Korean vocabulary pipeline.

What it does:

- streams Korean article dump `.bz2` shards directly
- tokenizes contiguous Hangul spans directly in Rust
- applies local Korean stopword lists
- supports a fast frequency/cutoff analysis mode
- can build `ko-game` artifacts compatible with the app runtime

Default vocab selection keeps all document frequencies unless you pass `--max-doc-ratio`.
This avoids dropping very common but still useful terms such as `한국` during the final
vocab build.

Analyze cutoff candidates:

```sh
cargo run --release -- \
  ../../data/ko/wikimedia/kowiki-latest-pages-articles1.xml-p1p147390.bz2 \
  --stopwords-dir ../../data/ko/wikimedia/stopwords \
  --limit-pages 2000 \
  --top-freq 40 \
  --sample-ranks 100,300,1000,3000,5000,10000,20000
```

Build game artifacts on a small sample:

```sh
cargo run --release -- \
  ../../data/ko/wikimedia/kowiki-latest-pages-articles1.xml-p1p147390.bz2 \
  --stopwords-dir ../../data/ko/wikimedia/stopwords \
  --limit-pages 200 \
  --max-vocab 5000 \
  --embedding-dim 64 \
  --build-output-dir ../../src/lib/generated/ko-game-rust-test
```

Build game artifacts from all downloaded shards:

```sh
cargo run --release -- \
  --all-pages-articles-shards \
  --input-dir ../../data/ko/wikimedia \
  --stopwords-dir ../../data/ko/wikimedia/stopwords \
  --min-count 10 \
  --max-vocab 30000 \
  --embedding-dim 256 \
  --build-output-dir ../../src/lib/generated/ko-game
```

Outputs in build mode:

- `vocab.json`
- `variants.json`
- `metadata.json`
- `embeddings.f32.*.bin`

Inspect built artifacts with `tools/game-vocab-tools`:

```sh
cd ../game-vocab-tools
uv run game-vocab-stats --game ko --rank-samples 100,300,1000,3000,5000,10000,20000
uv run game-vocab-neighbors --game ko 한국 역사
```

Notes:

- the progress bar is based on compressed bytes read, so it stays bounded during concurrent counting
- counting is parallelized by shard
- cooccurrence/build is currently single-process inside the Rust tool
- pass `--max-doc-ratio <value>` only if you intentionally want to drop ultra-common terms
- tokenization is based on Hangul spans rather than morphological analysis, so inspect the resulting vocab before replacing the production dataset
