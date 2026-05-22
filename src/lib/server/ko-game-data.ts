import { createGameData } from '$lib/server/create-game-data';

import categoriesAssetUrl from '../generated/ko-game/categories.json?url';
import metadataAssetUrl from '../generated/ko-game/metadata.json?url';
import variantsAssetUrl from '../generated/ko-game/variants.json?url';
import vocabAssetUrl from '../generated/ko-game/vocab.json?url';

const embedChunkGlob = import.meta.glob('../generated/ko-game/embeddings.f32.*.bin', {
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
	embedKeyPrefix: '../generated/ko-game',
	classifyRow: (row) => {
		if (row.doc_frequency >= 500) return '고빈도어';
		if (row.doc_frequency >= 200) return '일반어';
		return '한국어 어휘';
	},
	buildIntro: (row) =>
		`자주 쓰이는 한국어 단어입니다. 사용도 ${row.count}, 범위 ${row.doc_frequency}.`
});
