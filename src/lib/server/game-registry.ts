import type { GameId } from '$lib/game/types';

import * as ainGameData from '$lib/server/ain-game-data';
import * as jaGameData from '$lib/server/ja-game-data';
import * as zhGameData from '$lib/server/zh-game-data';

const gameModules = {
	zh: zhGameData,
	ja: jaGameData,
	ain: ainGameData
} as const;

export const getGameModule = (game: GameId) => gameModules[game];
