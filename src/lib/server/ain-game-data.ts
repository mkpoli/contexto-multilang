import { createGameData } from '$lib/server/create-game-data';

import categoriesAssetUrl from '../generated/ain-game/categories.json?url';
import metadataAssetUrl from '../generated/ain-game/metadata.json?url';
import variantsAssetUrl from '../generated/ain-game/variants.json?url';
import vocabAssetUrl from '../generated/ain-game/vocab.json?url';

const embedChunkGlob = import.meta.glob('../generated/ain-game/embeddings.f32.*.bin', {
	query: '?url',
	import: 'default',
	eager: true
}) as Record<string, string>;

export const { getRandomPuzzle, hasKnownWord, lookupGuess } = createGameData({
	metadataAssetUrl,
	vocabAssetUrl,
	variantsAssetUrl,
	categoriesAssetUrl,
	embedChunkGlob,
	embedKeyPrefix: '../generated/ain-game',
	normalizeLookupWord: (word) => word.replaceAll('_', ''),
	classifyRow: (row) => {
		if (row.doc_frequency >= 100) return 'Common Ainu word';
		if (row.doc_frequency >= 20) return 'Documented Ainu word';
		return 'Ainu word';
	},
	buildIntro: (row) =>
		`A commonly used Ainu word. Frequency ${row.count}, spread ${row.doc_frequency}.`
});
