## game-vocab-tools

Small inspection utilities for built game vocab artifacts under `src/lib/generated/*-game`.

Available commands:

- `uv run game-vocab-stats --game zh`
- `uv run game-vocab-neighbors --game zh <word> [more_words...]`

Examples:

```sh
uv run game-vocab-stats --game zh --top-freq 10
uv run game-vocab-stats --game ja --rank-samples 100,300,1000,3000,5000,10000,20000,30000,50000
uv run game-vocab-stats --game ja --rank-windows 10000,20000,30000 --window-radius 10
uv run game-vocab-neighbors --game zh 季節 歌曲
uv run game-vocab-neighbors --game ja --contains 季節 音楽
```

Notes:

- use `--game zh` or `--game ja` for the standard generated artifact directories
- use `--input-dir` to inspect a custom artifact directory instead
- `game-vocab-stats` handles corpus stats and cutoff analysis only
- `game-vocab-neighbors` handles query lookup and nearest-neighbor inspection only
- the Chinese and Japanese build pipelines live in `tools/zh-vocab-pipeline` and `tools/ja-vocab-pipeline`
