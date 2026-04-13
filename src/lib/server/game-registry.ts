import type { GameId } from '$lib/game/types';

import * as jaGameData from '$lib/server/ja-game-data';
import * as zhGameData from '$lib/server/zh-game-data';

const gameModules = {
	zh: zhGameData,
	ja: jaGameData
} as const;

export const getGameModule = (game: GameId) => gameModules[game];
