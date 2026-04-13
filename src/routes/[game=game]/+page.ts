import type { GameId } from '$lib/game/types';

export function load({ params }) {
	return {
		game: params.game as GameId
	};
}
