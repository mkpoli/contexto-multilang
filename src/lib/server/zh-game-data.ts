import { createGameData } from '$lib/server/create-game-data';

import metadataAssetUrl from '../generated/zh-game/metadata.json?url';
import variantsAssetUrl from '../generated/zh-game/variants.json?url';
import vocabAssetUrl from '../generated/zh-game/vocab.json?url';

const embedChunkGlob = import.meta.glob('../generated/zh-game/embeddings.f32.*.bin', {
	query: '?url',
	import: 'default',
	eager: true
}) as Record<string, string>;

export const { getRandomPuzzle, hasKnownWord, lookupGuess } = createGameData({
	metadataAssetUrl,
	vocabAssetUrl,
	variantsAssetUrl,
	embedChunkGlob,
	embedKeyPrefix: '../generated/zh-game',
	classifyRow: (row) => {
		if (row.doc_frequency >= 500) return '高頻詞';
		if (row.doc_frequency >= 200) return '常見詞';
		return '中文詞彙';
	},
	buildIntro: (row) => `這是一個常見中文詞。常見度 ${row.count}、分布度 ${row.doc_frequency}。`
});
