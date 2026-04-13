<script lang="ts">
	import GamePage from '$lib/components/game-page.svelte';
	import type { GameId } from '$lib/game/types';

	let { data } = $props<{ data: { game: GameId } }>();
</script>

<GamePage game={data.game} />
