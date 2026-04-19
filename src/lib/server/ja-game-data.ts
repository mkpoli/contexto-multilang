import { createGameData } from '$lib/server/create-game-data';

import metadataAssetUrl from '../generated/ja-game/metadata.json?url';
import variantsAssetUrl from '../generated/ja-game/variants.json?url';
import vocabAssetUrl from '../generated/ja-game/vocab.json?url';

const embedChunkGlob = import.meta.glob('../generated/ja-game/embeddings.f32.*.bin', {
	query: '?url',
	import: 'default',
	eager: true
}) as Record<string, string>;

export const { getRandomPuzzle, hasKnownWord, lookupGuess } = createGameData({
	metadataAssetUrl,
	vocabAssetUrl,
	variantsAssetUrl,
	embedChunkGlob,
	embedKeyPrefix: '../generated/ja-game',
	classifyRow: (row) => {
		if (row.doc_frequency >= 500) return '高頻語';
		if (row.doc_frequency >= 200) return '一般語';
		return '日本語語彙';
	},
	buildIntro: (row) =>
		`よく使われる日本語の単語です。出現度 ${row.count}、広がり ${row.doc_frequency}。`
});
