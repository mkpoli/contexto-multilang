export type Token = {
	surface: string;
	position: [number, number];
};

const PREFIXES = ['ku', 'k', 'en', 'in', 'ci', 'c', 'un', 'a', 'i', 'an', 'e', 'eci', 'ec'];
const SUFFIXES = ['an', 'as'];

const affixPattern = new RegExp(
	`((?:${PREFIXES.join('|')})=)?((?:${PREFIXES.join('|')})=)?([a-z/-]+)(=(?:${SUFFIXES.join('|')}))?`
);

function splitAffixes(word: string): string[] {
	if ((word.match(/=/g) ?? []).length + (word.match(/-/g) ?? []).length >= 2) {
		const parts = affixPattern.exec(word);
		if (!parts) return [word];
		return parts.slice(1).filter(Boolean);
	}

	const parts = word.split(/([-=])/);
	if (parts.length === 1) return [word];
	if (parts.length !== 3) return [word];
	const [a, sep, b] = parts;
	if (a.length > b.length) {
		return [a, `${sep}${b}`];
	}
	return [`${a}${sep}`, b];
}

function splitAffixingApostrophes(word: string): string[] {
	if (word.length < 2) return [word];
	const match = /^(['’‘])?([^'’‘]*)(['’‘])?$/.exec(word);
	if (!match) return [word];
	const [, prefix, middle, suffix] = match;
	if (prefix && suffix) return [prefix, middle, suffix];
	if (prefix) return [prefix, middle];
	if (suffix) return [middle, suffix];
	return [word];
}

function isWord(word: string): boolean {
	return /^[a-zA-Zâîûêôáíúéó=\-_'’\[\]]+$/.test(word) && /[a-zA-Zâîûêôáíúéó]/.test(word);
}

export function tokenize(inputText: string): Token[] {
	const pattern = /((?:\.\.\.(\.\.\.)?)|[a-zA-Zâîûêôáíúéó=\-_'’\[\]]+|\d+|[<>\.,‘"“”])|\s+/gu;
	const tokens: Token[] = [];
	for (const match of inputText.matchAll(pattern)) {
		if (!match) continue;
		const [surface] = match;
		if (!surface) continue;
		if (surface.match(/^\s+$/)) continue;
		const start = match.index!;
		let cursor = start;
		for (const apostrophePiece of splitAffixingApostrophes(surface)) {
			for (const affixPiece of splitAffixes(apostrophePiece)) {
				if (!affixPiece) continue;
				if (!isWord(affixPiece)) continue;
				const pieceStart = cursor;
				const pieceEnd = pieceStart + affixPiece.length;
				tokens.push({ surface: affixPiece, position: [pieceStart, pieceEnd] });
				cursor = pieceEnd;
			}
		}
	}
	return tokens;
}
