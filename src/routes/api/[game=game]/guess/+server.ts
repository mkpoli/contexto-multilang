import { json } from '@sveltejs/kit';

import { getGameModule } from '$lib/server/game-registry';

export async function POST({ params, request }) {
	const { answer, word } = (await request.json()) as {
		answer?: string;
		word?: string;
	};

	if (!answer || !word) {
		return json({ error: 'Missing answer or word.' }, { status: 400 });
	}

	const gameModule = getGameModule(params.game);

	return json({
		match: await gameModule.lookupGuess(answer, word),
		knownWord: await gameModule.hasKnownWord(word)
	});
}
