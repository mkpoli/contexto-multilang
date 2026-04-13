import { json } from '@sveltejs/kit';

import { getGameModule } from '$lib/server/game-registry';

export async function GET({ params }) {
	return json(await getGameModule(params.game).getRandomPuzzle());
}
