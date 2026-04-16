<script lang="ts">
	import { onMount } from 'svelte';

	import type { GamePuzzle, GuessLookupResponse, GuessProfile } from '$lib/game/types';

	type PageGame = 'zh' | 'ja' | 'ain';

	type GuessResult = GuessProfile & {
		order: number;
		state: 'hit' | 'known' | 'unknown' | 'duplicate';
	};

	type FeedbackTone = 'neutral' | 'warning' | 'success';

	type PersistedSession = {
		puzzle: GamePuzzle;
		guessCount: number;
		feedback: string;
		feedbackTone: FeedbackTone;
		history: GuessResult[];
		latestGuess: GuessResult | null;
		showClosestWords: boolean;
		showHint: boolean;
		rankHintUses: number;
		revealedCharacterHints: number[];
	};

	type GameCopy = {
		pageTitle: string;
		metaDescription: string;
		eyebrow: string;
		datasetName: string;
		freshTitle: string;
		startedTitle: string;
		intro: string;
		compactIntro: string;
		progressLabel: string;
		currentBuildLabel: string;
		categoryLabel: string;
		bestRankLabel: string;
		difficultyLabel: string;
		difficultyValue: string;
		startGuessingLabel: string;
		lengthHintLabel: string;
		proximityHintLabel: string;
		characterHintButton: string;
		newPuzzleLabel: string;
		submitGuessLabel: string;
		placeholder: string;
		hintLabel: string;
		answerLengthLabel: string;
		guessesLabel: string;
		statusLabel: string;
		solvedLabel: string;
		inProgressLabel: string;
		hiddenWordLabel: string;
		closestWordsLabel: string;
		showLabel: string;
		hideLabel: string;
		guessHistoryLabel: string;
		entriesSuffix: string;
		latestGuessLabel: string;
		emptyStateTitle: string;
		emptyStateBody: string;
		defaultFeedback: string;
		newPuzzleFeedback: string;
		loadFailedFeedback: string;
		loadingFeedback: string;
		emptyGuessFeedback: string;
		duplicateGuessFeedback: string;
		lookupFailedFeedback: string;
		knownWordUnmatchedFeedback: string;
		unknownWordFeedback: string;
		hintSolvedFeedback: string;
		hintAppliedFeedback: string;
		solvedFeedback: string;
		closeGuessFeedback: string;
		rankedGuessFeedback: string;
		lengthHintFeedback: string;
		proximityExhaustedFeedback: string;
		noMoreProximityFeedback: string;
		characterHintFeedback: string;
		proximityHintNote: string;
	};

	const format = (template: string, values: Record<string, string | number>) =>
		template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ''));

	let { game }: { game: PageGame } = $props();

	const GAME_COPY = {
		zh: {
			pageTitle: 'Contexto Multilang - 中文語義猜詞',
			metaDescription:
				'一個以中文維基百科語料為基礎的 Contexto 原型：猜詞、查看語義排名，並透過顏色感知接近程度。',
			eyebrow: 'Contexto Multilang / Chinese Prototype',
			datasetName: '中文 Wikipedia 5k 原型',
			freshTitle: '猜隱藏詞，不猜拼寫，猜語義。',
			startedTitle: '繼續縮小語義範圍。',
			intro:
				'系統會從一組高頻中文詞裡隨機挑出一個答案。你每猜一次，都會得到一個語義排名，越靠前代表越接近。',
			compactIntro: '猜測紀錄已按最相近到最遠排序，先追最前面的詞。',
			progressLabel: '本局進度',
			currentBuildLabel: '目前題目',
			categoryLabel: '類別',
			bestRankLabel: '目前最佳排名',
			difficultyLabel: '難度提示',
			difficultyValue: '答案來自高頻詞池',
			startGuessingLabel: '開始猜詞',
			lengthHintLabel: '提示',
			proximityHintLabel: '接近提示',
			characterHintButton: '第 {n} 字提示',
			newPuzzleLabel: '換一題',
			submitGuessLabel: '提交猜測',
			placeholder: '例如：季節、歌曲、北京',
			hintLabel: '提示',
			answerLengthLabel: '答案長度',
			guessesLabel: '已猜次數',
			statusLabel: '遊戲狀態',
			solvedLabel: '已猜中',
			inProgressLabel: '進行中',
			hiddenWordLabel: '隱藏詞',
			closestWordsLabel: '最接近的詞',
			showLabel: '顯示',
			hideLabel: '收起',
			guessHistoryLabel: '猜測記錄',
			entriesSuffix: '條',
			latestGuessLabel: '最新猜測',
			emptyStateTitle: '第一條記錄還沒出現。',
			emptyStateBody: '先試試輸入一個常見中文詞，例如「季節」或「歌曲」。',
			defaultFeedback: '輸入一個中文詞語，看看它離隱藏答案有多近。',
			newPuzzleFeedback: '新的一局開始了，繼續猜一個中文詞語。',
			loadFailedFeedback: '題目資料暫時載入失敗，請稍後重試。',
			loadingFeedback: '題目還在載入中。',
			emptyGuessFeedback: '先輸入一個中文詞語。',
			duplicateGuessFeedback: '你已經猜過「{word}」了，它目前排名第 {rank}。',
			lookupFailedFeedback: '查詢相似度時出了點問題，請再試一次。',
			knownWordUnmatchedFeedback:
				'「{word}」在資料庫裡，但目前還無法完成字詞匹配，請換一個近義詞再試。',
			unknownWordFeedback:
				'「{word}」目前不在可查詢的詞表中，這可能是因為太常見、太少見，或尚未收錄。請改試較具體的詞。',
			hintSolvedFeedback: '接近提示已自動加入，而且直接猜中了「{answer}」。',
			hintAppliedFeedback: '接近提示已自動加入「{word}」，目前排名第 {rank}。',
			solvedFeedback: '答對了，隱藏詞就是「{answer}」。{note}',
			closeGuessFeedback: '「{word}」很接近，目前排名第 {rank}。{note}',
			rankedGuessFeedback: '「{word}」目前排名第 {rank}。{note}',
			lengthHintFeedback: '提示：答案共有 {count} 個字。',
			proximityExhaustedFeedback: '接近提示已用完，最多只能使用 3 次。',
			noMoreProximityFeedback: '目前沒有更合適的接近提示了。',
			characterHintFeedback: '字元提示：第 {n} 個字是「{char}」。',
			proximityHintNote: '接近提示 {used}/{max}'
		},
		ja: {
			pageTitle: 'Contexto Multilang - 日本語プロトタイプ',
			metaDescription:
				'日本語版 Wikipedia コーパスを使った Contexto 風プロトタイプ。Vibrato で分かち書きし、正確な順位を返します。',
			eyebrow: 'Contexto Multilang / Japanese Prototype',
			datasetName: '日本語 Wikipedia 5k プロトタイプ',
			freshTitle: 'つづりではなく、意味で隠し語を当てる。',
			startedTitle: '意味の距離をさらに絞り込みましょう。',
			intro:
				'高頻度の日本語語彙からランダムに答えが選ばれます。推測するたびに意味的な順位が返り、数字が小さいほど近いです。',
			compactIntro: '推測履歴は近い順に並んでいます。まずは一番上を追ってください。',
			progressLabel: '進行状況',
			currentBuildLabel: '現在のセット',
			categoryLabel: 'カテゴリ',
			bestRankLabel: '現在の最高順位',
			difficultyLabel: '難易度ヒント',
			difficultyValue: '答えは高頻度語プールから出題',
			startGuessingLabel: '推測を始める',
			lengthHintLabel: '文字数ヒント',
			proximityHintLabel: '近さヒント',
			characterHintButton: '{n}文字目ヒント',
			newPuzzleLabel: '新しい問題',
			submitGuessLabel: '推測する',
			placeholder: '例：季節、音楽、東京',
			hintLabel: 'ヒント',
			answerLengthLabel: '答えの長さ',
			guessesLabel: '推測回数',
			statusLabel: '状態',
			solvedLabel: '正解',
			inProgressLabel: '進行中',
			hiddenWordLabel: '隠し語',
			closestWordsLabel: 'もっとも近い単語',
			showLabel: '表示',
			hideLabel: '閉じる',
			guessHistoryLabel: '推測履歴',
			entriesSuffix: '件',
			latestGuessLabel: '最新の推測',
			emptyStateTitle: 'まだ推測はありません。',
			emptyStateBody: 'まずは「季節」や「音楽」のような一般的な単語を入れてみてください。',
			defaultFeedback: '日本語の単語を入力して、隠し語にどれだけ近いか確かめてください。',
			newPuzzleFeedback: '新しい日本語パズルを用意しました。',
			loadFailedFeedback:
				'問題データの読み込みに失敗しました。しばらくしてからもう一度試してください。',
			loadingFeedback: '問題を読み込み中です。',
			emptyGuessFeedback: 'まず日本語の単語を入力してください。',
			duplicateGuessFeedback: '「{word}」はすでに推測済みです。現在の順位は {rank} 位です。',
			lookupFailedFeedback: '類似度の取得で問題が発生しました。もう一度試してください。',
			knownWordUnmatchedFeedback:
				'「{word}」はデータ内にありますが、うまく照合できませんでした。近い別の語を試してください。',
			unknownWordFeedback: '「{word}」は現在のデータセットにありません。別の単語を試してください。',
			hintSolvedFeedback: '近さヒントが自動入力され、そのまま「{answer}」を当てました。',
			hintAppliedFeedback: '近さヒントとして「{word}」を自動追加しました。現在 {rank} 位です。',
			solvedFeedback: '正解です。隠し語は「{answer}」です。{note}',
			closeGuessFeedback: '「{word}」はかなり近く、現在 {rank} 位です。{note}',
			rankedGuessFeedback: '「{word}」の現在順位は {rank} 位です。{note}',
			lengthHintFeedback: 'ヒント：答えは {count} 文字です。',
			proximityExhaustedFeedback: '近さヒントは使い切りました。最大 3 回までです。',
			noMoreProximityFeedback: 'これ以上ちょうどよい近さヒントはありません。',
			characterHintFeedback: '文字ヒント：{n} 文字目は「{char}」です。',
			proximityHintNote: '近さヒント {used}/{max}'
		},
		ain: {
			pageTitle: 'Contexto Multilang - Ainu Prototype',
			metaDescription:
				'A Contexto-style prototype built from an Ainu JSONL corpus with a simple word tokenizer.',
			eyebrow: 'Contexto Multilang / Ainu Prototype',
			datasetName: 'Ainu corpus prototype',
			freshTitle: 'Guess the hidden Ainu word by meaning.',
			startedTitle: 'Keep narrowing the semantic space.',
			intro:
				'A random answer is drawn from the Ainu corpus. Each guess returns an exact semantic rank, where smaller is closer.',
			compactIntro:
				'Your guesses are already sorted from closest to farthest. Push the best ranks first.',
			progressLabel: 'Progress',
			currentBuildLabel: 'Current dataset',
			categoryLabel: 'Category',
			bestRankLabel: 'Best rank',
			difficultyLabel: 'Difficulty hint',
			difficultyValue: 'Answer comes from the Ainu corpus answer pool',
			startGuessingLabel: 'Start guessing',
			lengthHintLabel: 'Length hint',
			proximityHintLabel: 'Proximity hint',
			characterHintButton: 'Character {n} hint',
			newPuzzleLabel: 'New puzzle',
			submitGuessLabel: 'Submit guess',
			placeholder: 'e.g. kamuy, aynu, mosir',
			hintLabel: 'Hint',
			answerLengthLabel: 'Answer length',
			guessesLabel: 'Guesses',
			statusLabel: 'Status',
			solvedLabel: 'Solved',
			inProgressLabel: 'In progress',
			hiddenWordLabel: 'Hidden word',
			closestWordsLabel: 'Closest words',
			showLabel: 'Show',
			hideLabel: 'Hide',
			guessHistoryLabel: 'Guess history',
			entriesSuffix: 'entries',
			latestGuessLabel: 'Latest guess',
			emptyStateTitle: 'No guesses yet.',
			emptyStateBody: 'Try a common Ainu word like "kamuy" or "aynu".',
			defaultFeedback: 'Enter an Ainu word to see how close it is to the hidden answer.',
			newPuzzleFeedback: 'A new Ainu puzzle is ready.',
			loadFailedFeedback: 'Failed to load the Ainu puzzle data. Please try again.',
			loadingFeedback: 'The puzzle is still loading.',
			emptyGuessFeedback: 'Enter an Ainu word first.',
			duplicateGuessFeedback: 'You already guessed "{word}". It is currently ranked #{rank}.',
			lookupFailedFeedback: 'There was a problem looking up similarity. Please try again.',
			knownWordUnmatchedFeedback:
				'"{word}" is in the dataset, but it could not be matched cleanly. Try a nearby word.',
			unknownWordFeedback: '"{word}" is not available in the current dataset. Try another word.',
			hintSolvedFeedback:
				'The proximity hint auto-submitted and solved the puzzle with "{answer}".',
			hintAppliedFeedback: 'The proximity hint auto-submitted "{word}", now ranked #{rank}.',
			solvedFeedback: 'Solved. The hidden word is "{answer}". {note}',
			closeGuessFeedback: '"{word}" is close, currently ranked #{rank}. {note}',
			rankedGuessFeedback: '"{word}" is currently ranked #{rank}. {note}',
			lengthHintFeedback: 'Hint: the answer is {count} characters long.',
			proximityExhaustedFeedback: 'No proximity hints remaining. Maximum: 3.',
			noMoreProximityFeedback: 'No better proximity hint is available right now.',
			characterHintFeedback: 'Character hint: character {n} is "{char}".',
			proximityHintNote: 'Proximity hint {used}/{max}'
		}
	} satisfies Record<PageGame, GameCopy>;

	const MAX_RANK_HINT_USES = 3;

	const normalize = (value: string) => value.trim().replace(/\s+/g, '');

	const rankTone = (rank: number) => {
		if (rank === 1) return 'tone-solved';
		if (rank <= 30) return 'tone-hot';
		if (rank <= 100) return 'tone-warm';
		if (rank <= 250) return 'tone-mild';
		return 'tone-cool';
	};

	const barFillPercent = (rank: number) => {
		if (rank <= 1) return 100;
		return Math.max(2, Math.min(100, Math.round(100 - Math.log10(rank) * 24)));
	};

	const loggedSimilarity = (rank: number) => {
		if (rank <= 1) return '1.000';
		return (1 / Math.log10(rank + 9)).toFixed(3);
	};

	const loggedSimilarityPercent = (rank: number) =>
		`${Math.round(Number(loggedSimilarity(rank)) * 100)}%`;

	const isCloseGuess = (rank: number) => rank <= 250;

	type CharacterHint = {
		char: string;
		state: 'exact' | 'present' | 'miss';
	};

	const getCharacterHints = (word: string, answer: string): CharacterHint[] => {
		const wordChars = [...word];
		const answerChars = [...answer];
		const answerCounts = new Map<string, number>();
		const result: CharacterHint[] = wordChars.map((char) => ({ char, state: 'miss' }));

		for (const char of answerChars) {
			answerCounts.set(char, (answerCounts.get(char) ?? 0) + 1);
		}

		for (let index = 0; index < wordChars.length; index += 1) {
			if (wordChars[index] === answerChars[index]) {
				result[index].state = 'exact';
				answerCounts.set(wordChars[index], (answerCounts.get(wordChars[index]) ?? 1) - 1);
			}
		}

		for (let index = 0; index < wordChars.length; index += 1) {
			if (result[index].state === 'exact') continue;
			const remaining = answerCounts.get(wordChars[index]) ?? 0;
			if (remaining > 0) {
				result[index].state = 'present';
				answerCounts.set(wordChars[index], remaining - 1);
			}
		}

		return result;
	};

	const sortHistory = (entries: GuessResult[]) =>
		[...entries].sort(
			(a, b) => a.rank - b.rank || b.similarity - a.similarity || a.order - b.order
		);

	let puzzle = $state<GamePuzzle | null>(null);
	let guess = $state('');
	let guessCount = $state(0);
	let feedback = $state('');
	let feedbackTone = $state<FeedbackTone>('neutral');
	let history = $state<GuessResult[]>([]);
	let latestGuess = $state<GuessResult | null>(null);
	let showClosestWords = $state(false);
	let showHint = $state(false);
	let rankHintUses = $state(0);
	let revealedCharacterHints = $state<number[]>([]);
	let loadingPuzzle = $state(true);
	let sessionReady = false;
	let initializedGame: PageGame | null = null;
	let loadVersion = 0;

	let gameCopy = $derived(GAME_COPY[game]);
	let sessionStorageKey = $derived(`contexto-multilang:${game}-session`);
	let apiBase = $derived(`/api/${game}`);
	let hasStarted = $derived(history.length > 0);
	let solved = $derived(history.some((entry) => entry.rank === 1));
	let bestRank = $derived(history.length ? Math.min(...history.map((entry) => entry.rank)) : null);
	let answerLength = $derived(puzzle ? [...puzzle.answer].length : 0);
	let rankHintUsesRemaining = $derived(MAX_RANK_HINT_USES - rankHintUses);
	let revealedClosestWords = $derived(solved && puzzle ? puzzle.closestWords.slice(0, 8) : []);
	let canShowLengthHint = $derived(!showHint && !solved);
	let canShowRankHint = $derived(!solved && rankHintUses < MAX_RANK_HINT_USES);
	let canRevealCharacter = $derived(
		!solved &&
			answerLength >= 2 &&
			rankHintUses >= MAX_RANK_HINT_USES &&
			revealedCharacterHints.length < answerLength - 1
	);
	let nextCharacterToReveal = $derived(
		canRevealCharacter
			? ([...Array(answerLength - 1).keys()].find((i) => !revealedCharacterHints.includes(i + 1)) ??
					-1) + 1
			: -1
	);

	function pickRankHint(): GuessProfile | null {
		if (!puzzle) return null;

		const guessedWords = new Set(history.map((entry) => entry.word));
		const candidates = puzzle.closestWords.filter(
			(entry) => entry.rank > 1 && !guessedWords.has(entry.word)
		);
		if (candidates.length === 0) return null;

		if (bestRank === null) {
			return (
				candidates.find((entry) => entry.rank >= 120 && entry.rank <= 320) ??
				candidates.find((entry) => entry.rank >= 80 && entry.rank <= 420) ??
				candidates[candidates.length - 1]
			);
		}

		const betterCandidates = candidates
			.filter((entry) => entry.rank < bestRank)
			.sort((a, b) => b.rank - a.rank || a.similarity - b.similarity);

		if (betterCandidates.length === 0) return null;

		const windows = [
			Math.max(15, Math.floor(bestRank * 0.15)),
			Math.max(35, Math.floor(bestRank * 0.3)),
			Math.max(70, Math.floor(bestRank * 0.5)),
			bestRank
		];
		for (const window of windows) {
			const nearby = betterCandidates.find((entry) => entry.rank >= Math.max(2, bestRank - window));
			if (nearby) return nearby;
		}

		return betterCandidates[0] ?? null;
	}

	function applyGuessResult(match: GuessProfile, source: 'user' | 'hint') {
		guessCount += 1;
		const nextGuess = {
			...match,
			order: guessCount,
			state: match.rank === 1 ? 'hit' : 'known'
		} satisfies GuessResult;
		history = sortHistory([...history, nextGuess]);
		latestGuess = nextGuess;

		if (source === 'hint') {
			feedback =
				match.rank === 1
					? format(gameCopy.hintSolvedFeedback, { answer: puzzle?.answer ?? '' })
					: format(gameCopy.hintAppliedFeedback, { word: match.word, rank: match.rank });
			feedbackTone = match.rank === 1 ? 'success' : 'neutral';
			return;
		}

		feedback =
			match.rank === 1
				? format(gameCopy.solvedFeedback, { answer: puzzle?.answer ?? '', note: match.note ?? '' })
				: format(
						isCloseGuess(match.rank) ? gameCopy.closeGuessFeedback : gameCopy.rankedGuessFeedback,
						{
							word: match.word,
							rank: match.rank,
							note: match.note ?? ''
						}
					);
		feedbackTone = match.rank === 1 ? 'success' : 'neutral';
	}

	function restoreSession(): boolean {
		const raw = localStorage.getItem(sessionStorageKey);
		if (!raw) return false;

		try {
			const session = JSON.parse(raw) as PersistedSession;
			if (!session?.puzzle?.answer || !Array.isArray(session.history)) {
				localStorage.removeItem(sessionStorageKey);
				return false;
			}

			puzzle = session.puzzle;
			guessCount = session.guessCount;
			feedback = session.feedback;
			feedbackTone = session.feedbackTone;
			history = sortHistory(session.history);
			latestGuess = session.latestGuess;
			showClosestWords = session.showClosestWords;
			showHint = session.showHint;
			rankHintUses = session.rankHintUses ?? 0;
			revealedCharacterHints = session.revealedCharacterHints ?? [];
			loadingPuzzle = false;
			return true;
		} catch {
			localStorage.removeItem(sessionStorageKey);
			return false;
		}
	}

	function persistSession() {
		if (!sessionReady || !puzzle) return;

		const session: PersistedSession = {
			puzzle,
			guessCount,
			feedback,
			feedbackTone,
			history,
			latestGuess,
			showClosestWords,
			showHint,
			rankHintUses,
			revealedCharacterHints
		};
		localStorage.setItem(sessionStorageKey, JSON.stringify(session));
	}

	function resetRuntimeState() {
		puzzle = null;
		guess = '';
		guessCount = 0;
		history = [];
		latestGuess = null;
		showClosestWords = false;
		showHint = false;
		rankHintUses = 0;
		revealedCharacterHints = [];
		feedbackTone = 'neutral';
		loadingPuzzle = true;
	}

	async function loadPuzzle() {
		const currentLoadVersion = ++loadVersion;
		loadingPuzzle = true;
		try {
			const response = await fetch(`${apiBase}/puzzle`);
			if (!response.ok) throw new Error('Failed to load puzzle');
			const nextPuzzle = (await response.json()) as GamePuzzle;
			if (currentLoadVersion != loadVersion) return;
			puzzle = nextPuzzle;
			guessCount = 0;
			history = [];
			latestGuess = null;
			showClosestWords = false;
			showHint = false;
			rankHintUses = 0;
			revealedCharacterHints = [];
			feedback = gameCopy.newPuzzleFeedback;
			feedbackTone = 'neutral';
		} catch {
			if (currentLoadVersion != loadVersion) return;
			feedback = gameCopy.loadFailedFeedback;
			feedbackTone = 'warning';
			puzzle = null;
		} finally {
			if (currentLoadVersion == loadVersion) {
				loadingPuzzle = false;
			}
		}
	}

	function initializeGameState() {
		loadVersion += 1;
		resetRuntimeState();
		feedback = gameCopy.defaultFeedback;
		if (!restoreSession()) {
			void loadPuzzle();
			return;
		}
		loadingPuzzle = false;
	}

	onMount(() => {
		sessionReady = true;
		initializeGameState();
		initializedGame = game;
	});

	$effect(() => {
		if (!sessionReady || initializedGame === null || initializedGame === game) return;
		initializeGameState();
		initializedGame = game;
	});

	$effect(() => {
		if (!sessionReady || initializedGame !== game) return;
		if (!puzzle) {
			localStorage.removeItem(sessionStorageKey);
			return;
		}
		persistSession();
	});

	async function submitGuess() {
		const word = normalize(guess);

		if (!puzzle) {
			feedback = gameCopy.loadingFeedback;
			feedbackTone = 'warning';
			return;
		}

		if (!word) {
			feedback = gameCopy.emptyGuessFeedback;
			feedbackTone = 'warning';
			return;
		}

		const existing = history.find((entry) => entry.word === word);
		if (existing) {
			feedback = format(gameCopy.duplicateGuessFeedback, { word, rank: existing.rank });
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const response = await fetch(`${apiBase}/guess`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ answer: puzzle.answerKey, word })
		});

		if (!response.ok) {
			feedback = gameCopy.lookupFailedFeedback;
			feedbackTone = 'warning';
			return;
		}

		const { match, knownWord } = (await response.json()) as GuessLookupResponse;
		if (!match) {
			feedback = knownWord
				? format(gameCopy.knownWordUnmatchedFeedback, { word })
				: format(gameCopy.unknownWordFeedback, { word });
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const matchKey = match.key ?? match.word;
		const canonicalExisting = history.find((entry) => (entry.key ?? entry.word) === matchKey);
		if (canonicalExisting) {
			feedback = format(gameCopy.duplicateGuessFeedback, {
				word,
				rank: canonicalExisting.rank
			});
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		applyGuessResult(match, 'user');
		guess = '';
	}

	async function resetGame() {
		guess = '';
		localStorage.removeItem(sessionStorageKey);
		await loadPuzzle();
	}

	function revealHint() {
		if (!puzzle || showHint) return;
		showHint = true;
		feedback = format(gameCopy.lengthHintFeedback, { count: answerLength });
		feedbackTone = 'neutral';
	}

	function revealRankHint() {
		if (!puzzle || solved) return;
		if (rankHintUses >= MAX_RANK_HINT_USES) {
			feedback = gameCopy.proximityExhaustedFeedback;
			feedbackTone = 'warning';
			return;
		}

		const nextHint = pickRankHint();
		if (!nextHint) {
			feedback = gameCopy.noMoreProximityFeedback;
			feedbackTone = 'warning';
			return;
		}

		rankHintUses += 1;
		applyGuessResult(
			{
				...nextHint,
				note: format(gameCopy.proximityHintNote, { used: rankHintUses, max: MAX_RANK_HINT_USES })
			},
			'hint'
		);
	}

	function revealCharacterHint() {
		if (!puzzle || solved || nextCharacterToReveal < 0) return;
		revealedCharacterHints = [...revealedCharacterHints, nextCharacterToReveal];
		const char = puzzle.answer[nextCharacterToReveal];
		feedback = format(gameCopy.characterHintFeedback, { n: nextCharacterToReveal + 1, char });
		feedbackTone = 'neutral';
	}
</script>

<svelte:head>
	<title>{gameCopy.pageTitle}</title>
	<meta name="description" content={gameCopy.metaDescription} />
</svelte:head>

<div class="page-shell">
	<section class:compact={hasStarted} class="hero-card">
		<div class="hero-copy">
			<div class="hero-topline">
				<p class="eyebrow">{gameCopy.eyebrow}</p>
				<div class="hero-controls">
					<a class="origin-link" href="https://contexto.me/en/" target="_blank" rel="noreferrer">
						原版遊戲 PT / EN / ES
					</a>
					<div class="switcher" aria-label="Game selector">
						<a class:active={game === 'zh'} href="/zh">ZH</a>
						<a class:active={game === 'ja'} href="/ja">JA</a>
						<a class:active={game === 'ain'} href="/ain">AIN</a>
					</div>
				</div>
			</div>
			<h1>{hasStarted ? gameCopy.startedTitle : gameCopy.freshTitle}</h1>
			{#if !hasStarted}
				<p class="lede">{gameCopy.intro}</p>
			{:else}
				<p class="lede compact-lede">{gameCopy.compactIntro}</p>
			{/if}
		</div>

		<div class="status-panel">
			<div>
				<span class="label">{hasStarted ? gameCopy.progressLabel : gameCopy.currentBuildLabel}</span
				>
				<strong
					>{hasStarted
						? `${history.length} ${gameCopy.entriesSuffix}`
						: gameCopy.datasetName}</strong
				>
				<p>{hasStarted || !puzzle ? feedback : puzzle.intro}</p>
			</div>
			<div>
				<span class="label">{gameCopy.categoryLabel}</span>
				<strong>{puzzle?.category ?? '...'}</strong>
			</div>
			<div>
				<span class="label">{hasStarted ? gameCopy.bestRankLabel : gameCopy.difficultyLabel}</span>
				<strong>{hasStarted ? `${bestRank ?? '—'}` : gameCopy.difficultyValue}</strong>
			</div>
		</div>
	</section>

	<section class="play-grid">
		<div class="play-card input-card">
			<div class="card-head">
				<h2>{gameCopy.startGuessingLabel}</h2>
				<div class="card-actions">
					{#if canShowLengthHint}
						<button class="ghost-button" type="button" onclick={revealHint}
							>{gameCopy.lengthHintLabel}</button
						>
					{/if}
					{#if canShowRankHint}
						<button class="ghost-button" type="button" onclick={revealRankHint}>
							{gameCopy.proximityHintLabel}
							{rankHintUsesRemaining}/{MAX_RANK_HINT_USES}
						</button>
					{/if}
					{#if canRevealCharacter && nextCharacterToReveal >= 0}
						<button class="ghost-button" type="button" onclick={revealCharacterHint}>
							{format(gameCopy.characterHintButton, { n: nextCharacterToReveal + 1 })}
						</button>
					{/if}
					<button class="ghost-button" type="button" onclick={resetGame} disabled={loadingPuzzle}
						>{gameCopy.newPuzzleLabel}</button
					>
				</div>
			</div>

			<form
				class="guess-form"
				onsubmit={(event) => {
					event.preventDefault();
					submitGuess();
				}}
			>
				<label class="sr-only" for="guess">{gameCopy.startGuessingLabel}</label>
				<input
					id="guess"
					bind:value={guess}
					maxlength="24"
					placeholder={gameCopy.placeholder}
					autocomplete="off"
					disabled={solved || loadingPuzzle || !puzzle}
				/>
				<button type="submit" disabled={solved || loadingPuzzle || !puzzle}
					>{gameCopy.submitGuessLabel}</button
				>
			</form>

			<p class={`feedback feedback-${feedbackTone}`}>{feedback}</p>

			{#if showHint}
				<div class="hint-panel">
					<span class="label">{gameCopy.hintLabel}</span>
					<strong>{gameCopy.answerLengthLabel}：{answerLength}</strong>
				</div>
			{/if}

			<div class="mini-stats">
				<div>
					<span class="label">{gameCopy.guessesLabel}</span>
					<strong>{guessCount}</strong>
				</div>
				<div>
					<span class="label">{gameCopy.bestRankLabel}</span>
					<strong>{bestRank ?? '—'}</strong>
				</div>
				<div>
					<span class="label">{gameCopy.statusLabel}</span>
					<strong>{solved ? gameCopy.solvedLabel : gameCopy.inProgressLabel}</strong>
				</div>
			</div>

			{#if solved}
				<div class="answer-banner">
					<span>{gameCopy.hiddenWordLabel}</span>
					<strong>{puzzle?.answer}</strong>
				</div>

				<div class="reveal-card">
					<div class="card-head reveal-head">
						<h2>{gameCopy.closestWordsLabel}</h2>
						<button
							class="ghost-button reveal-toggle"
							type="button"
							onclick={() => (showClosestWords = !showClosestWords)}
						>
							{showClosestWords ? gameCopy.hideLabel : gameCopy.showLabel}
						</button>
					</div>
					{#if showClosestWords}
						<div class="history-list reveal-list">
							{#each revealedClosestWords as entry}
								<article
									class={`guess-row ${rankTone(entry.rank)}`}
									title={`相似度 ${entry.similarity}%｜對數 ${loggedSimilarityPercent(entry.rank)}`}
								>
									<div
										class="heat-fill"
										style={`clip-path: inset(0 ${100 - barFillPercent(entry.rank)}% 0 0);`}
										aria-hidden="true"
									></div>
									<div class="guess-main">
										<div class="guess-word-group">
											<p class="guess-word">
												{#each getCharacterHints(entry.word, puzzle?.answer ?? '') as charHint}
													<span class={`guess-char char-${charHint.state}`}>{charHint.char}</span>
												{/each}
											</p>
										</div>
										<div class="guess-rank"><span>#{entry.rank}</span></div>
									</div>
								</article>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<div class="play-card history-card">
			<div class="card-head">
				<h2>{gameCopy.guessHistoryLabel}</h2>
				<span>{history.length} {gameCopy.entriesSuffix}</span>
			</div>

			{#if latestGuess}
				<div class="latest-guess-block">
					<div class="latest-guess-header">
						<span class="label">{gameCopy.latestGuessLabel}</span>
					</div>
					<article
						class={`guess-row guess-row-featured ${rankTone(latestGuess.rank)}`}
						title={`相似度 ${latestGuess.similarity}%｜對數 ${loggedSimilarityPercent(latestGuess.rank)}`}
					>
						<div
							class="heat-fill"
							style={`clip-path: inset(0 ${100 - barFillPercent(latestGuess.rank)}% 0 0);`}
							aria-hidden="true"
						></div>
						<div class="guess-main">
							<div class="guess-word-group">
								<p class="guess-word">
									{#each getCharacterHints(latestGuess.word, puzzle?.answer ?? '') as charHint}
										<span class={`guess-char char-${charHint.state}`}>{charHint.char}</span>
									{/each}
								</p>
							</div>
							<div class="guess-rank"><span>#{latestGuess.rank}</span></div>
						</div>
					</article>
					<div
						class="latest-guess-separator latest-guess-separator-bottom"
						aria-hidden="true"
					></div>
				</div>
			{/if}

			{#if history.length === 0}
				<div class="empty-state">
					<p>{gameCopy.emptyStateTitle}</p>
					<p>{gameCopy.emptyStateBody}</p>
				</div>
			{:else}
				<div class="history-list">
					{#each history as entry}
						<article
							class={`guess-row ${rankTone(entry.rank)}`}
							title={`相似度 ${entry.similarity}%｜對數 ${loggedSimilarityPercent(entry.rank)}`}
						>
							<div
								class="heat-fill"
								style={`clip-path: inset(0 ${100 - barFillPercent(entry.rank)}% 0 0);`}
								aria-hidden="true"
							></div>
							<div class="guess-main">
								<div class="guess-word-group">
									<p class="guess-word">
										{#each getCharacterHints(entry.word, puzzle?.answer ?? '') as charHint}
											<span class={`guess-char char-${charHint.state}`}>{charHint.char}</span>
										{/each}
									</p>
								</div>
								<div class="guess-rank"><span>#{entry.rank}</span></div>
							</div>
						</article>
					{/each}
				</div>
			{/if}
		</div>
	</section>
</div>
