/**
 * The stale-while-revalidate cache behind the tag track lists (genre, label, podcast, festival,
 * year, lineup, the songs and sets lists) and the search results page: the first page of each
 * list, keyed by exactly the query that produced it.
 *
 * Why it exists: going back to a genre seen a minute ago used to cost a full round trip with the
 * previous genre's rows standing under the new name meanwhile (issue #109). With this, a revisit
 * shows the list at once and refreshes it in the background, and a press on a genre card can
 * start the request before the page exists (docs/designs/perceived-performance/technical.md,
 * "Tag lists and search").
 *
 * A separate instance from the entity cache on purpose: a list is keyed by its whole query, so
 * the two never share keys, and clearing one (a filter reset, a test) need not clear the other.
 * Memory only, like the entity cache; a failed load is never cached.
 */
import { credentials } from "./store.js";
import { createEntityCache } from "./entityCache.js";
import { fetchSpotifyTracksPage } from "./trackPages.js";
import { listOf, subsonicJson } from "./subsonic.js";

/** The one cache the list pages read and write. */
export const trackListCache = createEntityCache({ maxEntries: 60 });

// Another account on the same device must never see the first one's lists.
let cachedFor = null;
credentials.subscribe((value) => {
  const username = value?.username ?? "";
  if (cachedFor !== null && cachedFor !== username) trackListCache.clear();
  cachedFor = username;
});

/**
 * A stable key for a query object: the entries sorted by name, undefined ones dropped, so two
 * objects asking the same question always make the same key.
 *
 * @param {string} kind - What is listed: `tracks`, or the Subsonic method of a search section.
 * @param {Record<string, unknown>} params
 * @returns {string}
 */
export function listKey(kind, params) {
  const parts = Object.keys(params)
    .filter((name) => params[name] !== undefined && params[name] !== null && params[name] !== "")
    .sort()
    .map((name) => `${name}=${String(params[name])}`);
  return `${kind}?${parts.join("&")}`;
}

/**
 * The key of a track list's first page. The page size and whether versions are folded together
 * change what the first page holds, so both are part of it.
 *
 * @param {Record<string, unknown>} params - The list's query, without `offset`/`count`.
 * @param {{pageSize: number, dedupe: boolean}} options
 * @returns {string}
 */
export function trackListKey(params, { pageSize, dedupe }) {
  return listKey("tracks", {
    ...params,
    count: pageSize,
    dedupeVersions: dedupe ? "1" : undefined,
  });
}

/**
 * The first page of a `getSpotifyTracks` list, in the shape the cache stores: the rows, where the
 * list continues, and the version keys seen so far (as entries, so the page can rebuild its own
 * map and keep folding versions together on "load more").
 *
 * @param {Record<string, unknown>} params
 * @param {{pageSize: number, dedupe: boolean, signal?: AbortSignal}} options
 * @returns {Promise<{tracks: object[], nextOffset: number, hasMore: boolean, seen: Array<[string, object]>|null}>}
 */
export async function fetchFirstTrackPage(params, { pageSize, dedupe, signal }) {
  const seen = dedupe ? new Map() : null;
  const page = await fetchSpotifyTracksPage(params, 0, { pageSize, seen, signal });
  return { ...page, seen: seen ? [...seen.entries()] : null };
}

/**
 * Starts loading a track list's first page into the cache without showing it anywhere -- the
 * press on a genre, label... card. Shares a request already under way for the same query and
 * asks nothing when a fresh copy is cached, so one press is at most one request. A failure is
 * swallowed: the page that opens reports its own.
 *
 * @param {Record<string, unknown>} params
 * @param {{pageSize: number, dedupe: boolean}} options
 */
export function prefetchTrackList(params, options) {
  trackListCache
    .load(trackListKey(params, options), () => fetchFirstTrackPage(params, options))
    .catch(() => {});
}

/**
 * The first page of a `getAlbumList2`/`getArtistList` search, for the search results page.
 *
 * @param {'getAlbumList2'|'getArtistList'} method
 * @param {Record<string, unknown>} params
 * @param {string} path - Where the rows sit in the answer, e.g. `albumList2.album`.
 * @param {{signal?: AbortSignal}} [options]
 * @returns {Promise<object[]>}
 */
export async function fetchListPage(method, params, path, { signal } = {}) {
  return listOf(await subsonicJson(method, params, { signal }), path);
}
