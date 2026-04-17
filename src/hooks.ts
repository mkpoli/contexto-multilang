import { deLocalizeUrl } from '$lib/paraglide/runtime';

const GAME_ROUTE_PREFIXES = ['/zh', '/ja', '/ko', '/ain'];

export const reroute = (request) => {
	const url = new URL(request.url);
	if (
		GAME_ROUTE_PREFIXES.some(
			(prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`)
		)
	) {
		return url.pathname;
	}

	return deLocalizeUrl(request.url).pathname;
};
