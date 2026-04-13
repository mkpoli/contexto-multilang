import { json } from '@sveltejs/kit';

import { getRandomPuzzle } from '$lib/server/zh-game-data';

export async function GET() {
	return json(await getRandomPuzzle());
}
