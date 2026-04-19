import { read } from '$app/server';
import type { GamePuzzle, GuessProfile } from '$lib/game/types';

type Metadata = {
	vocab_size: number;
	embedding_dim: number;
	playable_ids: number[];
	total_pages: number;
	min_count: number;
	max_vocab: number;
	window_size: number;
	explained_variance: number;
	embed_chunks: number;
};

type VocabRow = {
	word: string;
	display_word?: string;
	count: number;
	doc_frequency: number;
};

type LoadedGameData = {
	metadata: Metadata;
	vocab: VocabRow[];
	wordToId: Map<string, number>;
	lookupToIds: Map<string, number[]>;
	embeddings: Float32Array;
	playableIds: number[];
};

type AnswerCache = {
	ranks: Uint32Array;
	scores: Uint16Array;
	neighbors: GuessProfile[];
};

type CreateGameDataOptions = {
	metadataAssetUrl: string;
	vocabAssetUrl: string;
	variantsAssetUrl: string;
	embedChunkGlob: Record<string, string>;
	embedKeyPrefix: string;
	classifyRow: (row: VocabRow) => string;
	buildIntro: (row: VocabRow) => string;
	displayWord?: (row: VocabRow) => string;
	normalizeLookupWord?: (word: string) => string;
};

const MAX_CACHED_ANSWERS = 24;
const MIN_PLAYABLE_DOC_FREQUENCY = 200;

const toPercent = (score: number) => Math.max(1, Math.min(100, Math.round(score * 100)));
const toScoreBasisPoints = (score: number) =>
	Math.max(0, Math.min(10000, Math.round(((score + 1) / 2) * 10000)));
const fromScoreBasisPoints = (value: number) => (value / 10000) * 2 - 1;

export const createGameData = ({
	metadataAssetUrl,
	vocabAssetUrl,
	variantsAssetUrl,
	embedChunkGlob,
	embedKeyPrefix,
	classifyRow,
	buildIntro,
	displayWord = (row) => row.display_word ?? row.word,
	normalizeLookupWord = (word) => word
}: CreateGameDataOptions) => {
	const answerCache = new Map<number, AnswerCache>();
	let dataPromise: Promise<LoadedGameData> | null = null;

	const appendLookupIds = (lookupToIds: Map<string, number[]>, word: string, ids: number[]) => {
		const normalizedWord = normalizeLookupWord(word);
		const existingIds = lookupToIds.get(normalizedWord);
		if (!existingIds) {
			lookupToIds.set(normalizedWord, [...ids]);
			return;
		}

		for (const id of ids) {
			if (!existingIds.includes(id)) {
				existingIds.push(id);
			}
		}
	};

	const loadGameData = async (): Promise<LoadedGameData> => {
		if (!dataPromise) {
			dataPromise = (async () => {
				const [metadataText, vocabText, variantsText] = await Promise.all([
					read(metadataAssetUrl).text(),
					read(vocabAssetUrl).text(),
					read(variantsAssetUrl).text()
				]);

				const metadata = JSON.parse(metadataText) as Metadata;
				const vocab = JSON.parse(vocabText) as VocabRow[];
				const variantRows = JSON.parse(variantsText) as Record<string, number[]>;
				const wordToId = new Map(vocab.map((entry, index) => [entry.word, index]));
				const lookupToIds = new Map<string, number[]>();
				for (const [word, ids] of Object.entries(variantRows)) {
					appendLookupIds(lookupToIds, word, ids);
				}
				for (const [index, entry] of vocab.entries()) {
					appendLookupIds(lookupToIds, entry.word, [index]);
				}

				const chunkCount = metadata.embed_chunks ?? 1;
				const chunkUrls = Array.from({ length: chunkCount }, (_, i) => {
					const key = `${embedKeyPrefix}/embeddings.f32.${i}.bin`;
					const url = embedChunkGlob[key];
					if (!url) {
						throw new Error(`Missing embedding chunk: ${key}`);
					}
					return url;
				});
				const chunkBuffers = await Promise.all(chunkUrls.map((url) => read(url).arrayBuffer()));

				const totalFloats = chunkBuffers.reduce((sum, buf) => sum + buf.byteLength / 4, 0);
				const embeddings = new Float32Array(totalFloats);
				let offset = 0;
				for (const buf of chunkBuffers) {
					embeddings.set(new Float32Array(buf), offset);
					offset += buf.byteLength / 4;
				}

				return {
					metadata,
					vocab,
					wordToId,
					lookupToIds,
					embeddings,
					playableIds: metadata.playable_ids
				};
			})();
		}

		return dataPromise;
	};

	const buildAnswerCache = (answerId: number, data: LoadedGameData): AnswerCache => {
		const { embeddings, metadata, vocab } = data;
		const { embedding_dim: embeddingDim, vocab_size: vocabSize } = metadata;
		const answerStart = answerId * embeddingDim;
		const answerVector = embeddings.subarray(answerStart, answerStart + embeddingDim);

		const scorePairs: Array<{ id: number; score: number }> = new Array(vocabSize);
		for (let wordId = 0; wordId < vocabSize; wordId += 1) {
			const offset = wordId * embeddingDim;
			let dot = 0;
			for (let dim = 0; dim < embeddingDim; dim += 1) {
				dot += answerVector[dim] * embeddings[offset + dim];
			}
			scorePairs[wordId] = { id: wordId, score: dot };
		}

		scorePairs.sort((left, right) => right.score - left.score || left.id - right.id);

		const ranks = new Uint32Array(vocabSize);
		const scores = new Uint16Array(vocabSize);
		const neighbors: GuessProfile[] = [];

		for (let rank = 0; rank < scorePairs.length; rank += 1) {
			const pair = scorePairs[rank];
			const finalRank = rank + 1;
			ranks[pair.id] = finalRank;
			scores[pair.id] = toScoreBasisPoints(pair.score);

			if (pair.id !== answerId && neighbors.length < 12) {
				neighbors.push({
					word: displayWord(vocab[pair.id]),
					rank: finalRank,
					similarity: toPercent(pair.score)
				});
			}
		}

		return { ranks, scores, neighbors };
	};

	const getAnswerCache = async (
		answer: string
	): Promise<{ answerId: number; cache: AnswerCache; data: LoadedGameData } | null> => {
		const data = await loadGameData();
		const answerId = data.wordToId.get(answer);
		if (answerId === undefined) {
			return null;
		}

		let cache = answerCache.get(answerId);
		if (!cache) {
			cache = buildAnswerCache(answerId, data);
			answerCache.set(answerId, cache);
			if (answerCache.size > MAX_CACHED_ANSWERS) {
				const oldestKey = answerCache.keys().next().value;
				if (oldestKey !== undefined) {
					answerCache.delete(oldestKey);
				}
			}
			return { answerId, cache, data };
		}

		answerCache.delete(answerId);
		answerCache.set(answerId, cache);
		return { answerId, cache, data };
	};

	const resolveGuessIds = (data: LoadedGameData, word: string): number[] => {
		const variantIds = data.lookupToIds.get(normalizeLookupWord(word));
		if (variantIds && variantIds.length > 0) {
			return variantIds;
		}

		const exactId = data.wordToId.get(word);
		return exactId === undefined ? [] : [exactId];
	};

	return {
		getRandomPuzzle: async (): Promise<GamePuzzle> => {
			const data = await loadGameData();
			const baseSource =
				data.playableIds.length > 0 ? data.playableIds : data.vocab.map((_, index) => index);
			const source = baseSource.filter(
				(id) => data.vocab[id]?.doc_frequency >= MIN_PLAYABLE_DOC_FREQUENCY
			);
			const answerPool = source.length > 0 ? source : baseSource;
			const answerId = answerPool[Math.floor(Math.random() * answerPool.length)];
			const row = data.vocab[answerId];
			const cache = (await getAnswerCache(row.word))?.cache;

			return {
				answer: displayWord(row),
				answerKey: row.word,
				category: classifyRow(row),
				frequencyBand: 'high',
				intro: buildIntro(row),
				closestWords: cache?.neighbors ?? []
			};
		},

		lookupGuess: async (answer: string, word: string): Promise<GuessProfile | null> => {
			const bundle = await getAnswerCache(answer);
			if (!bundle) {
				return null;
			}

			const candidateIds = resolveGuessIds(bundle.data, word);
			if (candidateIds.length === 0) {
				return null;
			}

			let guessId = candidateIds[0];
			for (const candidateId of candidateIds) {
				if (bundle.cache.ranks[candidateId] < bundle.cache.ranks[guessId]) {
					guessId = candidateId;
				}
			}

			const canonicalRow = bundle.data.vocab[guessId];
			const canonicalWord = canonicalRow.word;
			const shownWord = displayWord(canonicalRow);
			const guessedWord = canonicalWord === word ? shownWord : word;

			if (guessId === bundle.answerId) {
				return {
					word: guessedWord,
					key: canonicalWord,
					rank: 1,
					similarity: 100,
					note: undefined
				};
			}

			return {
				word: guessedWord,
				key: canonicalWord,
				rank: bundle.cache.ranks[guessId],
				similarity: toPercent(fromScoreBasisPoints(bundle.cache.scores[guessId])),
				note: undefined
			};
		},

		hasKnownWord: async (word: string): Promise<boolean> => {
			const data = await loadGameData();
			return data.lookupToIds.has(normalizeLookupWord(word)) || data.wordToId.has(word);
		}
	};
};
