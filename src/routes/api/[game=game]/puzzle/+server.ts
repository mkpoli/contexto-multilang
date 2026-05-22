import { json } from '@sveltejs/kit';

import { DEFAULT_DIFFICULTY, isDifficulty } from '$lib/game/types';
import { getGameModule } from '$lib/server/game-registry';

export async function GET({ params, url }) {
	const raw = url.searchParams.get('difficulty');
	const difficulty = isDifficulty(raw) ? raw : DEFAULT_DIFFICULTY;
	return json(await getGameModule(params.game).getRandomPuzzle(difficulty));
}
