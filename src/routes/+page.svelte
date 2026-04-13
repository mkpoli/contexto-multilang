<script lang="ts">
	import { onMount } from 'svelte';

	import type { GamePuzzle, GuessLookupResponse, GuessProfile } from '$lib/game/zh-game';

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

	const SESSION_STORAGE_KEY = 'contexto-multilang:zh-session';
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
			if (result[index].state === 'exact') {
				continue;
			}

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
	let feedback = $state('輸入一個中文詞語，看看它離隱藏答案有多近。');
	let feedbackTone = $state<FeedbackTone>('neutral');
	let history = $state<GuessResult[]>([]);
	let latestGuess = $state<GuessResult | null>(null);
	let showClosestWords = $state(false);
	let showHint = $state(false);
	let rankHintUses = $state(0);
	let revealedCharacterHints = $state<number[]>([]);
	let loadingPuzzle = $state(true);
	let sessionReady = false;

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
		if (!puzzle) {
			return null;
		}

		const guessedWords = new Set(history.map((entry) => entry.word));
		const candidates = puzzle.closestWords.filter(
			(entry) => entry.rank > 1 && !guessedWords.has(entry.word)
		);

		if (candidates.length === 0) {
			return null;
		}

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

		if (betterCandidates.length === 0) {
			return null;
		}

		const windows = [
			Math.max(15, Math.floor(bestRank * 0.15)),
			Math.max(35, Math.floor(bestRank * 0.3)),
			Math.max(70, Math.floor(bestRank * 0.5)),
			bestRank
		];

		for (const window of windows) {
			const nearby = betterCandidates.find((entry) => entry.rank >= Math.max(2, bestRank - window));
			if (nearby) {
				return nearby;
			}
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
					? `接近提示已自動加入，而且直接猜中了「${puzzle?.answer}」。`
					: `接近提示已自動加入「${match.word}」，目前排名第 ${match.rank}。`;
			feedbackTone = match.rank === 1 ? 'success' : 'neutral';
			return;
		}

		feedback =
			match.rank === 1
				? match.note
					? `答對了，隱藏詞就是「${puzzle?.answer}」。${match.note}`
					: `答對了，隱藏詞就是「${puzzle?.answer}」。`
				: match.note
					? `「${match.word}」很接近，目前排名第 ${match.rank}。${match.note}`
					: `「${match.word}」很接近，目前排名第 ${match.rank}。`;
		feedbackTone = match.rank === 1 ? 'success' : 'neutral';
	}

	function restoreSession(): boolean {
		const raw = localStorage.getItem(SESSION_STORAGE_KEY);
		if (!raw) {
			return false;
		}

		try {
			const session = JSON.parse(raw) as PersistedSession;
			if (!session?.puzzle?.answer || !Array.isArray(session.history)) {
				localStorage.removeItem(SESSION_STORAGE_KEY);
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
			localStorage.removeItem(SESSION_STORAGE_KEY);
			return false;
		}
	}

	function persistSession() {
		if (!sessionReady || !puzzle) {
			return;
		}

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
		localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
	}

	async function loadPuzzle() {
		loadingPuzzle = true;
		try {
			const response = await fetch('/api/puzzle');
			if (!response.ok) {
				throw new Error('Failed to load puzzle');
			}
			puzzle = (await response.json()) as GamePuzzle;
			guessCount = 0;
			history = [];
			latestGuess = null;
			showClosestWords = false;
			showHint = false;
			rankHintUses = 0;
			revealedCharacterHints = [];
			feedback = '新的一局開始了，繼續猜一個中文詞語。';
			feedbackTone = 'neutral';
		} catch {
			feedback = '題目資料暫時載入失敗，請稍後重試。';
			feedbackTone = 'warning';
			puzzle = null;
		} finally {
			loadingPuzzle = false;
		}
	}

	onMount(() => {
		sessionReady = true;
		if (!restoreSession()) {
			void loadPuzzle();
		}
	});

	$effect(() => {
		if (!sessionReady) {
			return;
		}

		if (!puzzle) {
			localStorage.removeItem(SESSION_STORAGE_KEY);
			return;
		}

		persistSession();
	});

	async function submitGuess() {
		const word = normalize(guess);

		if (!puzzle) {
			feedback = '題目還在載入中。';
			feedbackTone = 'warning';
			return;
		}

		if (!word) {
			feedback = '先輸入一個中文詞語。';
			feedbackTone = 'warning';
			return;
		}

		const existing = history.find((entry) => entry.word === word);
		if (existing) {
			feedback = `你已經猜過「${word}」了，它目前排名第 ${existing.rank}。`;
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const response = await fetch('/api/guess', {
			method: 'POST',
			headers: {
				'content-type': 'application/json'
			},
			body: JSON.stringify({ answer: puzzle.answerKey, word })
		});

		if (!response.ok) {
			feedback = '查詢相似度時出了點問題，請再試一次。';
			feedbackTone = 'warning';
			return;
		}

		const { match, knownWord } = (await response.json()) as GuessLookupResponse;

		if (!match) {
			feedback = knownWord
				? `「${word}」在資料庫裡，但目前還無法完成字詞匹配，請換一個近義詞再試。`
				: `我們目前不知道「${word}」的相似度，請換一個資料庫裡已有的詞。`;
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const canonicalExisting = history.find((entry) => entry.word === match.word);
		if (canonicalExisting) {
			feedback = `你已經猜過「${match.word}」了，它目前排名第 ${canonicalExisting.rank}。`;
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		applyGuessResult(match, 'user');
		guess = '';
	}

	async function resetGame() {
		guess = '';
		localStorage.removeItem(SESSION_STORAGE_KEY);
		await loadPuzzle();
	}

	function revealHint() {
		if (!puzzle || showHint) {
			return;
		}

		showHint = true;
		feedback = `提示：答案共有 ${answerLength} 個字。`;
		feedbackTone = 'neutral';
	}

	function revealRankHint() {
		if (!puzzle || solved) {
			return;
		}

		if (rankHintUses >= MAX_RANK_HINT_USES) {
			feedback = '接近提示已用完，最多只能使用 3 次。';
			feedbackTone = 'warning';
			return;
		}

		const nextHint = pickRankHint();
		if (!nextHint) {
			feedback = '目前沒有更合適的接近提示了。';
			feedbackTone = 'warning';
			return;
		}

		rankHintUses += 1;
		applyGuessResult(
			{ ...nextHint, note: `接近提示 ${rankHintUses}/${MAX_RANK_HINT_USES}` },
			'hint'
		);
	}

	function revealCharacterHint() {
		if (!puzzle || solved || nextCharacterToReveal < 0) {
			return;
		}

		const targetChar = puzzle.answer[nextCharacterToReveal];
		const guessedWordWithChar = history.find((entry) => entry.word.includes(targetChar));

		revealedCharacterHints = [...revealedCharacterHints, nextCharacterToReveal];

		if (guessedWordWithChar) {
			feedback = `字元提示：答案包含某個你已猜過的字。`;
		} else {
			feedback = `字元提示：答案包含某個你尚未猜到的字。`;
		}
		feedbackTone = 'neutral';
	}
</script>

<svelte:head>
	<title>Contexto Multilang - 中文語義猜詞</title>
	<meta
		name="description"
		content="一個以中文維基百科語料為基礎的 Contexto 原型：猜詞、查看語義排名，並透過顏色感知接近程度。"
	/>
</svelte:head>

<div class="page-shell">
	<section class:compact={hasStarted} class="hero-card">
		<div class="hero-copy">
			<div class="hero-topline">
				<p class="eyebrow">Contexto Multilang / Chinese Prototype</p>
				<a class="origin-link" href="https://contexto.me/en/" target="_blank" rel="noreferrer">
					原版遊戲 PT / EN / ES
				</a>
			</div>
			<h1>{hasStarted ? '繼續縮小語義範圍。' : '猜隱藏詞，不猜拼寫，猜語義。'}</h1>
			{#if !hasStarted}
				<p class="lede">
					系統會從一組高頻中文詞裡隨機挑出一個答案。你每猜一次，都會得到一個語義排名，越靠前代表越接近。
				</p>
			{:else}
				<p class="lede compact-lede">猜測紀錄已按最相近到最遠排序，先追最前面的詞。</p>
			{/if}
		</div>

		<div class="status-panel">
			<div>
				<span class="label">{hasStarted ? '本局進度' : '目前題目'}</span>
				<strong>{hasStarted ? `${history.length} 條有效猜測` : '中文 Wikipedia 5k 原型'}</strong>
				<p>{hasStarted || !puzzle ? feedback : puzzle.intro}</p>
			</div>
			<div>
				<span class="label">類別</span>
				<strong>{puzzle?.category ?? '載入中'}</strong>
			</div>
			<div>
				<span class="label">{hasStarted ? '目前最佳排名' : '難度提示'}</span>
				<strong>{hasStarted ? `${bestRank ?? '—'}` : '答案來自高頻詞池'}</strong>
			</div>
		</div>
	</section>

	<section class="play-grid">
		<div class="play-card input-card">
			<div class="card-head">
				<h2>開始猜詞</h2>
				<div class="card-actions">
					{#if canShowLengthHint}
						<button class="ghost-button" type="button" onclick={revealHint}> 提示 </button>
					{/if}
					{#if canShowRankHint}
						<button class="ghost-button" type="button" onclick={revealRankHint}>
							接近提示 {rankHintUsesRemaining}/{MAX_RANK_HINT_USES}
						</button>
					{/if}
					{#if canRevealCharacter && nextCharacterToReveal >= 0}
						<button class="ghost-button" type="button" onclick={revealCharacterHint}>
							第 {nextCharacterToReveal + 1} 字提示
						</button>
					{/if}
					<button class="ghost-button" type="button" onclick={resetGame} disabled={loadingPuzzle}>
						換一題
					</button>
				</div>
			</div>

			<form
				class="guess-form"
				onsubmit={(event) => {
					event.preventDefault();
					submitGuess();
				}}
			>
				<label class="sr-only" for="guess">輸入中文詞語</label>
				<input
					id="guess"
					bind:value={guess}
					maxlength="12"
					placeholder="例如：天氣、歌曲、北京"
					autocomplete="off"
					disabled={solved || loadingPuzzle || !puzzle}
				/>
				<button type="submit" disabled={solved || loadingPuzzle || !puzzle}>提交猜測</button>
			</form>

			<p class={`feedback feedback-${feedbackTone}`}>{feedback}</p>

			{#if showHint}
				<div class="hint-panel">
					<span class="label">提示</span>
					<strong>答案長度：{answerLength} 個字</strong>
				</div>
			{/if}

			<div class="mini-stats">
				<div>
					<span class="label">已猜次數</span>
					<strong>{guessCount}</strong>
				</div>
				<div>
					<span class="label">目前最佳排名</span>
					<strong>{bestRank ?? '—'}</strong>
				</div>
				<div>
					<span class="label">遊戲狀態</span>
					<strong>{solved ? '已猜中' : '進行中'}</strong>
				</div>
			</div>

			{#if solved}
				<div class="answer-banner">
					<span>隱藏詞</span>
					<strong>{puzzle?.answer}</strong>
				</div>

				<div class="reveal-card">
					<div class="card-head reveal-head">
						<h2>最接近的詞</h2>
						<button
							class="ghost-button reveal-toggle"
							type="button"
							onclick={() => (showClosestWords = !showClosestWords)}
						>
							{showClosestWords ? '收起' : '顯示'}
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
										<div class="guess-rank">
											<span>#{entry.rank}</span>
										</div>
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
				<h2>猜測記錄</h2>
				<span>{history.length} 條</span>
			</div>

			{#if latestGuess}
				<div class="latest-guess-block">
					<div class="latest-guess-header">
						<span class="label">最新猜測</span>
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
							<div class="guess-rank">
								<span>#{latestGuess.rank}</span>
							</div>
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
					<p>第一條記錄還沒出現。</p>
					<p>先試試輸入一個常見中文詞，例如「季節」或「歌曲」。</p>
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
								<div class="guess-rank">
									<span>#{entry.rank}</span>
								</div>
							</div>
						</article>
					{/each}
				</div>
			{/if}
		</div>
	</section>
</div>
