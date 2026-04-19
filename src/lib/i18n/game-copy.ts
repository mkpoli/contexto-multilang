import type { GameId } from '$lib/game/types';
import * as m from '$lib/paraglide/messages';
import { locales } from '$lib/paraglide/runtime';

type GameLocale = (typeof locales)[number];

export type GameCopy = {
	pageTitle: string;
	metaDescription: string;
	eyebrow: string;
	freshTitle: string;
	startedTitle: string;
	intro: string;
	compactIntro: string;
	bestRankLabel: string;
	startGuessingLabel: string;
	lengthHintLabel: string;
	proximityHintLabel: string;
	characterHintButton: string;
	newPuzzleLabel: string;
	submitGuessLabel: string;
	placeholder: string;
	hintLabel: string;
	answerLengthValue: string;
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
	originalGameLabel: string;
	gameSelectorLabel: string;
	similarityTitle: string;
};

const token = <Name extends string>(name: Name) => `{${name}}`;

export const GAME_LOCALES = {
	zh: 'zh-hant',
	ja: 'ja',
	ko: 'ko',
	ain: 'ain'
} satisfies Record<GameId, GameLocale>;

export const getGameLocale = (game: GameId) => GAME_LOCALES[game];

export const getGameCopy = (game: GameId): GameCopy => {
	const locale = getGameLocale(game);

	return {
		pageTitle: m.game_page_title({}, { locale }),
		metaDescription: m.game_meta_description({}, { locale }),
		eyebrow: m.game_eyebrow({}, { locale }),
		freshTitle: m.game_fresh_title({}, { locale }),
		startedTitle: m.game_started_title({}, { locale }),
		intro: m.game_intro({}, { locale }),
		compactIntro: m.game_compact_intro({}, { locale }),
		bestRankLabel: m.game_best_rank_label({}, { locale }),
		startGuessingLabel: m.game_start_guessing_label({}, { locale }),
		lengthHintLabel: m.game_length_hint_label({}, { locale }),
		proximityHintLabel: m.game_proximity_hint_label({}, { locale }),
		characterHintButton: m.game_character_hint_button({ n: token('n') }, { locale }),
		newPuzzleLabel: m.game_new_puzzle_label({}, { locale }),
		submitGuessLabel: m.game_submit_guess_label({}, { locale }),
		placeholder: m.game_placeholder({}, { locale }),
		hintLabel: m.game_hint_label({}, { locale }),
		answerLengthValue: m.game_answer_length_value({ count: token('count') }, { locale }),
		guessesLabel: m.game_guesses_label({}, { locale }),
		statusLabel: m.game_status_label({}, { locale }),
		solvedLabel: m.game_solved_label({}, { locale }),
		inProgressLabel: m.game_in_progress_label({}, { locale }),
		hiddenWordLabel: m.game_hidden_word_label({}, { locale }),
		closestWordsLabel: m.game_closest_words_label({}, { locale }),
		showLabel: m.game_show_label({}, { locale }),
		hideLabel: m.game_hide_label({}, { locale }),
		guessHistoryLabel: m.game_guess_history_label({}, { locale }),
		entriesSuffix: m.game_entries_suffix({}, { locale }),
		latestGuessLabel: m.game_latest_guess_label({}, { locale }),
		emptyStateTitle: m.game_empty_state_title({}, { locale }),
		emptyStateBody: m.game_empty_state_body({}, { locale }),
		defaultFeedback: m.game_default_feedback({}, { locale }),
		newPuzzleFeedback: m.game_new_puzzle_feedback({}, { locale }),
		loadFailedFeedback: m.game_load_failed_feedback({}, { locale }),
		loadingFeedback: m.game_loading_feedback({}, { locale }),
		emptyGuessFeedback: m.game_empty_guess_feedback({}, { locale }),
		duplicateGuessFeedback: m.game_duplicate_guess_feedback(
			{ word: token('word'), rank: token('rank') },
			{ locale }
		),
		lookupFailedFeedback: m.game_lookup_failed_feedback({}, { locale }),
		knownWordUnmatchedFeedback: m.game_known_word_unmatched_feedback(
			{ word: token('word') },
			{ locale }
		),
		unknownWordFeedback: m.game_unknown_word_feedback({ word: token('word') }, { locale }),
		hintSolvedFeedback: m.game_hint_solved_feedback({ answer: token('answer') }, { locale }),
		hintAppliedFeedback: m.game_hint_applied_feedback(
			{ word: token('word'), rank: token('rank') },
			{ locale }
		),
		solvedFeedback: m.game_solved_feedback(
			{ answer: token('answer'), note: token('note') },
			{ locale }
		),
		closeGuessFeedback: m.game_close_guess_feedback(
			{ word: token('word'), rank: token('rank'), note: token('note') },
			{ locale }
		),
		rankedGuessFeedback: m.game_ranked_guess_feedback(
			{ word: token('word'), rank: token('rank'), note: token('note') },
			{ locale }
		),
		lengthHintFeedback: m.game_length_hint_feedback({ count: token('count') }, { locale }),
		proximityExhaustedFeedback: m.game_proximity_exhausted_feedback({}, { locale }),
		noMoreProximityFeedback: m.game_no_more_proximity_feedback({}, { locale }),
		characterHintFeedback: m.game_character_hint_feedback(
			{ n: token('n'), char: token('char') },
			{ locale }
		),
		proximityHintNote: m.game_proximity_hint_note(
			{ used: token('used'), max: token('max') },
			{ locale }
		),
		originalGameLabel: m.game_original_link_label({}, { locale }),
		gameSelectorLabel: m.game_selector_label({}, { locale }),
		similarityTitle: m.game_similarity_title(
			{ similarity: token('similarity'), percent: token('percent') },
			{ locale }
		)
	};
};
