export type GuessProfile = {
	word: string;
	rank: number;
	similarity: number;
	note?: string;
};

export type MockPuzzle = {
	answer: string;
	category: string;
	frequencyBand: 'high';
	intro: string;
	guesses: GuessProfile[];
};

const fallbackRanksByCategory: Record<string, number> = {
	季節: 460,
	文化: 430,
	地點: 400
};

export const mockChinesePuzzles: MockPuzzle[] = [
	{
		answer: '春天',
		category: '季節',
		frequencyBand: 'high',
		intro: '一個常見、溫和、充滿變化的日常詞。',
		guesses: [
			{ word: '春天', rank: 1, similarity: 100, note: '猜中了' },
			{ word: '夏天', rank: 18, similarity: 88 },
			{ word: '冬天', rank: 24, similarity: 84 },
			{ word: '秋天', rank: 29, similarity: 81 },
			{ word: '季節', rank: 35, similarity: 78 },
			{ word: '天氣', rank: 57, similarity: 71 },
			{ word: '花', rank: 73, similarity: 66 },
			{ word: '溫暖', rank: 91, similarity: 63 },
			{ word: '陽光', rank: 118, similarity: 58 },
			{ word: '公園', rank: 164, similarity: 51 },
			{ word: '節日', rank: 214, similarity: 44 },
			{ word: '雨', rank: 276, similarity: 38 },
			{ word: '學校', rank: 401, similarity: 27 }
		]
	},
	{
		answer: '音樂',
		category: '文化',
		frequencyBand: 'high',
		intro: '一個經常出現在生活、娛樂與學習裡的高頻詞。',
		guesses: [
			{ word: '音樂', rank: 1, similarity: 100, note: '猜中了' },
			{ word: '歌曲', rank: 12, similarity: 91 },
			{ word: '唱歌', rank: 19, similarity: 87 },
			{ word: '旋律', rank: 27, similarity: 83 },
			{ word: '樂器', rank: 34, similarity: 80 },
			{ word: '鋼琴', rank: 56, similarity: 73 },
			{ word: '聲音', rank: 79, similarity: 68 },
			{ word: '節奏', rank: 104, similarity: 62 },
			{ word: '舞蹈', rank: 141, similarity: 56 },
			{ word: '電影', rank: 198, similarity: 48 },
			{ word: '快樂', rank: 252, similarity: 41 },
			{ word: '耳機', rank: 311, similarity: 35 },
			{ word: '電腦', rank: 487, similarity: 22 }
		]
	},
	{
		answer: '城市',
		category: '地點',
		frequencyBand: 'high',
		intro: '一個非常常見的空間概念詞，也適合做中文示例題。',
		guesses: [
			{ word: '城市', rank: 1, similarity: 100, note: '猜中了' },
			{ word: '地方', rank: 14, similarity: 89 },
			{ word: '北京', rank: 17, similarity: 88 },
			{ word: '上海', rank: 23, similarity: 85 },
			{ word: '街道', rank: 41, similarity: 77 },
			{ word: '建築', rank: 58, similarity: 72 },
			{ word: '公園', rank: 86, similarity: 65 },
			{ word: '交通', rank: 109, similarity: 61 },
			{ word: '人口', rank: 147, similarity: 55 },
			{ word: '鄉村', rank: 193, similarity: 49 },
			{ word: '生活', rank: 238, similarity: 43 },
			{ word: '地圖', rank: 322, similarity: 33 },
			{ word: '桌子', rank: 520, similarity: 18 }
		]
	}
];

export const mockChineseVocabulary = Array.from(
	new Set(
		mockChinesePuzzles.flatMap((puzzle) => [
			puzzle.answer,
			...puzzle.guesses.map((guess) => guess.word)
		])
	)
).sort((a, b) => a.localeCompare(b, 'zh-Hant'));

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export const lookupMockGuess = (puzzle: MockPuzzle, word: string): GuessProfile | null => {
	const exactMatch = puzzle.guesses.find((entry) => entry.word === word);
	if (exactMatch) {
		return exactMatch;
	}

	if (!mockChineseVocabulary.includes(word)) {
		return null;
	}

	const answerChars = new Set([...puzzle.answer]);
	const sharedChars = [...new Set([...word])].filter((char) => answerChars.has(char)).length;
	const puzzleIndex = mockChinesePuzzles.findIndex((entry) => entry.answer === puzzle.answer);
	const wordIndex = mockChineseVocabulary.indexOf(word);
	const seed = ((puzzleIndex + 1) * 37 + (wordIndex + 3) * 17) % 41;
	const similarity = clamp(
		18 + sharedChars * 16 + (word.length === puzzle.answer.length ? 4 : 0) + seed,
		18,
		52
	);
	const rankBase = fallbackRanksByCategory[puzzle.category] ?? 480;
	const rank = clamp(rankBase - similarity * 3 - sharedChars * 12 + seed, 160, 520);

	return {
		word,
		rank,
		similarity,
		note: 'mock-fallback'
	};
};
