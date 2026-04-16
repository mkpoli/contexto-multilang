export type GameId = 'zh' | 'ja' | 'ain';

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
	intro: string;
	closestWords: GuessProfile[];
};

export type GuessLookupResponse = {
	match: GuessProfile | null;
	knownWord: boolean;
};
