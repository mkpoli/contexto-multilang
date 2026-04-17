## game-vocab-tools

Small inspection utilities for built game vocab artifacts under `src/lib/generated/*-game`.

Available commands:

- `uv run game-vocab-stats --game zh`
- `uv run game-vocab-neighbors --game zh <word> [more_words...]`
- `uv run game-vocab-stats --game ko`

Examples:

```sh
uv run game-vocab-stats --game zh --top-freq 10
uv run game-vocab-stats --game ja --rank-samples 100,300,1000,3000,5000,10000,20000,30000,50000
uv run game-vocab-stats --game ko --rank-samples 100,300,1000,3000,5000,10000,20000
uv run game-vocab-stats --game ja --rank-windows 10000,20000,30000 --window-radius 10
uv run game-vocab-neighbors --game zh 季節 歌曲
uv run game-vocab-neighbors --game ja --contains 季節 音楽
uv run game-vocab-neighbors --game ko 한국 역사
```

Notes:

- use `--game zh`, `--game ja`, or `--game ko` for the standard generated artifact directories
- use `--input-dir` to inspect a custom artifact directory instead
- `game-vocab-stats` handles corpus stats and cutoff analysis only
- `game-vocab-neighbors` handles query lookup and nearest-neighbor inspection only
- the Chinese, Japanese, and Korean build pipelines live in `tools/zh-vocab-pipeline`, `tools/ja-vocab-pipeline`, and `tools/ko-vocab-pipeline`
