export type GameId = 'zh' | 'ja' | 'ko' | 'ain';

export const DIFFICULTIES = ['easy', 'medium', 'hard'] as const;
export type Difficulty = (typeof DIFFICULTIES)[number];
export const DEFAULT_DIFFICULTY: Difficulty = 'medium';

export const isDifficulty = (value: unknown): value is Difficulty =>
	typeof value === 'string' && (DIFFICULTIES as readonly string[]).includes(value);

export type GuessProfile = {
	word: string;
	key?: string;
	rank: number;
	similarity: number;
	note?: string;
};

export type GamePuzzle = {
	answer: string;
	answerKey: string;
	category: string;
	frequencyBand: 'high';
	difficulty: Difficulty;
	intro: string;
	closestWords: GuessProfile[];
};

export type GuessLookupResponse = {
	match: GuessProfile | null;
	knownWord: boolean;
};
