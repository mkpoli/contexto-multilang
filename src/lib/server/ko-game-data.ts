import { createGameData } from '$lib/server/create-game-data';

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
	embedChunkGlob,
	embedKeyPrefix: '../generated/ko-game',
	classifyRow: (row) => {
		if (row.doc_frequency >= 500) return '고빈도어';
		if (row.doc_frequency >= 200) return '일반어';
		return '한국어 어휘';
	},
	buildIntro: (row) =>
		`한국어 위키백과 말뭉치 기반. 출현 빈도 ${row.count}, 등장 문서 수 ${row.doc_frequency}.`
});
