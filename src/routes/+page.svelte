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
		rankHint: GuessProfile | null;
	};

	const SESSION_STORAGE_KEY = 'contexto-multilang:zh-session';

	const normalize = (value: string) => value.trim().replace(/\s+/g, '');

	const rankTone = (rank: number) => {
		if (rank === 1) return 'tone-solved';
		if (rank <= 30) return 'tone-hot';
		if (rank <= 100) return 'tone-warm';
		if (rank <= 250) return 'tone-mild';
		return 'tone-cool';
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
	let rankHint = $state<GuessProfile | null>(null);
	let loadingPuzzle = $state(true);
	let sessionReady = false;

	let hasStarted = $derived(history.length > 0);
	let solved = $derived(history.some((entry) => entry.rank === 1));
	let bestRank = $derived(history.length ? Math.min(...history.map((entry) => entry.rank)) : null);
	let answerLength = $derived(puzzle ? [...puzzle.answer].length : 0);
	let revealedClosestWords = $derived(solved && puzzle ? puzzle.closestWords.slice(0, 8) : []);

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
				candidates.find((entry) => entry.rank >= 80 && entry.rank <= 180) ??
				candidates.find((entry) => entry.rank >= 40 && entry.rank <= 220) ??
				candidates[0]
			);
		}

		const nearbyBetter =
			candidates.find(
				(entry) => entry.rank < bestRank && entry.rank >= Math.max(2, bestRank - 30)
			) ??
			candidates.find(
				(entry) => entry.rank < bestRank && entry.rank >= Math.max(2, bestRank - 60)
			) ??
			candidates.find(
				(entry) => entry.rank < bestRank && entry.rank >= Math.max(2, bestRank - 100)
			);

		return nearbyBetter ?? null;
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
			rankHint = session.rankHint;
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
			rankHint
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
			rankHint = null;
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
		guessCount += 1;

		if (!match) {
			guessCount -= 1;
			feedback = knownWord
				? `「${word}」在資料庫裡，但目前還無法完成字詞匹配，請換一個近義詞再試。`
				: `我們目前不知道「${word}」的相似度，請換一個資料庫裡已有的詞。`;
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const canonicalExisting = history.find((entry) => entry.word === match.word);
		if (canonicalExisting) {
			guessCount -= 1;
			feedback = `你已經猜過「${match.word}」了，它目前排名第 ${canonicalExisting.rank}。`;
			feedbackTone = 'warning';
			guess = '';
			return;
		}

		const nextGuess = {
			...match,
			order: guessCount,
			state: match.rank === 1 ? 'hit' : 'known'
		} satisfies GuessResult;

		history = sortHistory([...history, nextGuess]);
		latestGuess = nextGuess;

		feedback =
			match.rank === 1
				? match.note
					? `答對了，隱藏詞就是「${puzzle.answer}」。${match.note}`
					: `答對了，隱藏詞就是「${puzzle.answer}」。`
				: match.note
					? `「${match.word}」很接近，目前排名第 ${match.rank}。${match.note}`
					: `「${match.word}」很接近，目前排名第 ${match.rank}。`;
		feedbackTone = match.rank === 1 ? 'success' : 'neutral';
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

		const nextHint = pickRankHint();
		if (!nextHint) {
			feedback = '目前沒有更合適的接近提示了。';
			feedbackTone = 'warning';
			return;
		}

		rankHint = nextHint;
		feedback = `接近提示：可以試試「${nextHint.word}」，它的排名是 #${nextHint.rank}。`;
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
			<p class="eyebrow">Contexto Multilang / Chinese Prototype</p>
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
					<button
						class="ghost-button"
						type="button"
						onclick={revealHint}
						disabled={loadingPuzzle || !puzzle || showHint || solved}
					>
						{showHint ? '已顯示提示' : '提示'}
					</button>
					<button
						class="ghost-button"
						type="button"
						onclick={revealRankHint}
						disabled={loadingPuzzle || !puzzle || solved}
					>
						接近提示
					</button>
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

			{#if rankHint && !solved}
				<div class="hint-panel rank-hint-panel">
					<span class="label">接近提示</span>
					<strong>試試「{rankHint.word}」</strong>
					<p>它目前排名第 #{rankHint.rank}。</p>
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
								<article class={`guess-row ${rankTone(entry.rank)}`}>
									<div
										class="heat-fill"
										style={`clip-path: inset(0 ${100 - entry.similarity}% 0 0);`}
										aria-hidden="true"
									></div>
									<div class="guess-main">
										<p class="guess-word">{entry.word}</p>
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
					<article class={`guess-row guess-row-featured ${rankTone(latestGuess.rank)}`}>
						<div
							class="heat-fill"
							style={`clip-path: inset(0 ${100 - latestGuess.similarity}% 0 0);`}
							aria-hidden="true"
						></div>
						<div class="guess-main">
							<p class="guess-word">{latestGuess.word}</p>
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
						<article class={`guess-row ${rankTone(entry.rank)}`}>
							<div
								class="heat-fill"
								style={`clip-path: inset(0 ${100 - entry.similarity}% 0 0);`}
								aria-hidden="true"
							></div>
							<div class="guess-main">
								<p class="guess-word">{entry.word}</p>
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
