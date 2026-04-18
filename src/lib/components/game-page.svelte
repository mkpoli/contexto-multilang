<script lang="ts">
	import { onMount } from 'svelte';

	import { getGameCopy } from '$lib/i18n/game-copy';
	import type { GameId, GamePuzzle, GuessLookupResponse, GuessProfile } from '$lib/game/types';

	type GuessResult = GuessProfile & {
		order: number;
		state: 'hit' | 'known' | 'unknown' | 'duplicate';
	};

	type FeedbackTone = 'neutral' | 'warning' | 'success';

	type PersistedSession = {
		version?: number;
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

	const SESSION_VERSION = 2;

	const format = (template: string, values: Record<string, string | number>) =>
		template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ''));

	let { game }: { game: GameId } = $props();

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
	let initializedGame: GameId | null = null;
	let loadVersion = 0;

	let gameCopy = $derived(getGameCopy(game));
	let sessionStorageKey = $derived(`contexto-multilang:${game}-session`);
	let apiBase = $derived(`/api/${game}`);
	let hasStarted = $derived(history.length > 0);
	let solved = $derived(history.some((entry) => entry.rank === 1));
	let bestRank = $derived(history.length ? Math.min(...history.map((entry) => entry.rank)) : null);
	let answerCharacters = $derived(puzzle ? [...puzzle.answer] : []);
	let answerLength = $derived(answerCharacters.length);
	let rankHintUsesRemaining = $derived(MAX_RANK_HINT_USES - rankHintUses);
	let revealedClosestWords = $derived(solved && puzzle ? puzzle.closestWords.slice(0, 8) : []);
	let hasPersistentHints = $derived(showHint || revealedCharacterHints.length > 0);
	let revealedCharacterHintSet = $derived(new Set(revealedCharacterHints));
	let hintCharacters = $derived(
		answerCharacters.map((char, index) => ({
			char,
			index,
			revealed: revealedCharacterHintSet.has(index)
		}))
	);
	let canShowLengthHint = $derived(!showHint && !solved);
	let canShowRankHint = $derived(!solved && rankHintUses < MAX_RANK_HINT_USES);
	let nextCharacterToReveal = $derived.by(() => {
		if (!(!solved && answerLength >= 2 && rankHintUses >= MAX_RANK_HINT_USES)) {
			return -1;
		}

		const nextIndex = [...Array(answerLength - 1).keys()].find(
			(i) => !revealedCharacterHints.includes(i)
		);
		return nextIndex ?? -1;
	});
	let canRevealCharacter = $derived(
		!solved && answerLength >= 2 && rankHintUses >= MAX_RANK_HINT_USES && nextCharacterToReveal >= 0
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

			const answerChars = [...session.puzzle.answer];
			const maxRevealIndex = Math.max(-1, answerChars.length - 2);
			const usesLegacyCharacterHintState = (session.version ?? 0) < SESSION_VERSION;
			const normalizedRevealedCharacterHints = usesLegacyCharacterHintState
				? []
				: (session.revealedCharacterHints ?? []).filter(
						(index) => Number.isInteger(index) && index >= 0 && index <= maxRevealIndex
					);
			const hasLegacyCharacterHintFeedback = /第 0 個字|0 文字目|character 0|0번째 글자/.test(
				session.feedback ?? ''
			);

			puzzle = session.puzzle;
			guessCount = session.guessCount;
			feedback = hasLegacyCharacterHintFeedback ? gameCopy.defaultFeedback : session.feedback;
			feedbackTone = session.feedbackTone;
			history = sortHistory(session.history);
			latestGuess = session.latestGuess;
			showClosestWords = session.showClosestWords;
			showHint = session.showHint;
			rankHintUses = session.rankHintUses ?? 0;
			revealedCharacterHints = normalizedRevealedCharacterHints;
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
			version: SESSION_VERSION,
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
		const char = answerCharacters[nextCharacterToReveal];
		if (!char) return;
		revealedCharacterHints = [...revealedCharacterHints, nextCharacterToReveal];
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
						{gameCopy.originalGameLabel}
					</a>
					<div class="switcher" aria-label={gameCopy.gameSelectorLabel}>
						<a class:active={game === 'zh'} href="/zh">ZH</a>
						<a class:active={game === 'ja'} href="/ja">JA</a>
						<a class:active={game === 'ko'} href="/ko">KO</a>
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

			{#if hasPersistentHints && !solved}
				<div class="hint-panel">
					<span class="label">{gameCopy.hintLabel}</span>
					<strong>{format(gameCopy.answerLengthValue, { count: answerLength })}</strong>
					<div class="hint-characters" aria-label={gameCopy.hintLabel}>
						{#each hintCharacters as entry}
							<div class:revealed={entry.revealed} class="hint-character">
								<span class="hint-character-index">{entry.index + 1}</span>
								<strong>{entry.revealed ? entry.char : '·'}</strong>
							</div>
						{/each}
					</div>
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
									title={format(gameCopy.similarityTitle, {
										similarity: entry.similarity,
										percent: loggedSimilarityPercent(entry.rank)
									})}
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
						title={format(gameCopy.similarityTitle, {
							similarity: latestGuess.similarity,
							percent: loggedSimilarityPercent(latestGuess.rank)
						})}
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
							title={format(gameCopy.similarityTitle, {
								similarity: entry.similarity,
								percent: loggedSimilarityPercent(entry.rank)
							})}
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
