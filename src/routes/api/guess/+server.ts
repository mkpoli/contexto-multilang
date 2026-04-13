import { json } from '@sveltejs/kit';

import { hasKnownWord, lookupGuess } from '$lib/server/zh-game-data';

export async function POST({ request }) {
	const { answer, word } = (await request.json()) as {
		answer?: string;
		word?: string;
	};

	if (!answer || !word) {
		return json({ error: 'Missing answer or word.' }, { status: 400 });
	}

	return json({
		match: await lookupGuess(answer, word),
		knownWord: await hasKnownWord(word)
	});
}
