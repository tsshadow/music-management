import { get } from "svelte/store";
import { authParams, restUrl } from "./store.js";
import { listOf, subsonicJson } from "./subsonic.js";
import { deduplicateTracks, getDeduplicateKey } from "./deduplicate.js";

/**
 * The paged track sources a list page and a playing queue both read from
 * (docs/designs/list-continuation/).
 *
 * `fetchSpotifyTracksPage` is the page-filling loop the songs list (`Dashboard.svelte`) and the
 * artist page (`ArtistView.svelte`) each had a copy of. The `*Continuation` factories wrap a source
 * in the `{kind, cursor, fetchNext}` shape `listContinuation.js` tops a queue up with; each returns
 * null when the list has nothing more, so a list that fit on one page records no continuation.
 */

/**
 * Whether a paged answer says there is more.
 *
 * LMS sends `moreResults` as a boolean or as the string "true"; an older answer without it has
 * more when the page came back full.
 *
 * @param {unknown} moreResults
 * @param {number} got - How many rows the page held.
 * @param {number} pageSize - How many were asked for.
 * @returns {boolean}
 */
export function hasMoreResults(moreResults, got, pageSize) {
  if (moreResults !== undefined && moreResults !== null)
    return moreResults === true || String(moreResults) === "true";
  return got === pageSize;
}

/**
 * One page of `getSpotifyTracks`, filled to `pageSize` across calls when folding versions together
 * (`seen`) left the first call short.
 *
 * Stops on a call that neither returns a track nor moves the offset on, so a server that keeps
 * saying `moreResults` without progress cannot spin the loop.
 *
 * @param {Record<string, unknown>} params - The list's query, without `offset`/`count`.
 * @param {number} offset - Where to start.
 * @param {object} [options]
 * @param {number} [options.pageSize]
 * @param {Map<string, object>|null} [options.seen] - Version keys already shown; updated in place.
 *   Null skips folding versions together.
 * @param {AbortSignal} [options.signal]
 * @param {typeof subsonicJson} [options.fetchJson] - Injected by the tests.
 * @returns {Promise<{tracks: object[], nextOffset: number, hasMore: boolean}>}
 * @throws Whatever `subsonicJson` throws; the page decides what a failure means.
 */
export async function fetchSpotifyTracksPage(
  params,
  offset,
  { pageSize = 50, seen = null, signal, fetchJson = subsonicJson } = {},
) {
  const tracks = [];
  let cursor = Number(offset) || 0;
  let hasMore = true;
  while (tracks.length < pageSize && hasMore) {
    const data = await fetchJson(
      "getSpotifyTracks",
      { ...params, offset: cursor, count: pageSize },
      { signal },
    );
    const node = data?.["subsonic-response"]?.tracks;
    const got = listOf(data, "tracks.track");
    const kept = seen ? deduplicateTracks(got, seen) : got;
    if (seen) for (const track of kept) seen.set(getDeduplicateKey(track), track);
    tracks.push(...kept);

    hasMore = hasMoreResults(node?.moreResults, got.length, pageSize);
    const next =
      node?.nextOffset !== undefined && node?.nextOffset !== null
        ? Number(node.nextOffset)
        : cursor + got.length;
    if (got.length === 0 && !(next > cursor)) hasMore = false;
    cursor = next;
  }
  return { tracks, nextOffset: cursor, hasMore };
}

/**
 * A `getSpotifyTracks` list as a continuation: the songs and sets lists with every sort and
 * filter, a genre, label, podcast, festival, year or lineup, search results, an artist.
 *
 * A snapshot of the query at the moment playback started: a filter changed on the page afterwards
 * does not change what the playing queue continues with.
 *
 * @param {Record<string, unknown>} params - The list's query, without `offset`/`count`.
 * @param {number|null} offset - Where the list continues; null when it does not.
 * @param {{pageSize?: number, dedupe?: boolean, kind?: string, fetchJson?: typeof subsonicJson}} [options]
 *   `dedupe` folds versions of a song together against the queue, as the page does against itself.
 * @returns {object|null}
 */
export function spotifyTracksContinuation(
  params,
  offset,
  { pageSize = 50, dedupe = false, kind = "songs", fetchJson = subsonicJson } = {},
) {
  if (offset === null || offset === undefined) return null;
  const query = { ...params };
  return {
    kind,
    cursor: offset,
    async fetchNext(cursor, { queue = [] } = {}) {
      const seen = dedupe ? new Map(queue.map((track) => [getDeduplicateKey(track), track])) : null;
      try {
        const page = await fetchSpotifyTracksPage(query, cursor, { pageSize, seen, fetchJson });
        return { tracks: page.tracks, cursor: page.hasMore ? page.nextOffset : null };
      } catch (error) {
        console.warn("Could not load the next page of a track list", error);
        return { tracks: [], cursor, failed: true };
      }
    },
  };
}

/**
 * A `getSongs` query as a continuation: a preset (a dynamic playlist) and the car-mode mix.
 *
 * `build(offset, count)` returns the `{method, params}` to ask; a random query must carry the seed
 * its first page used, so the next page is the rest of the same shuffle and not a new one that
 * repeats it. A page shorter than asked is the last.
 *
 * @param {(offset: number, count: number) => {method: string, params: Record<string, unknown>}} build
 * @param {number|null} offset - Where the list continues; null when it does not.
 * @param {{pageSize?: number, kind?: string, fetchJson?: typeof subsonicJson}} [options]
 * @returns {object|null}
 */
export function getSongsContinuation(
  build,
  offset,
  { pageSize = 100, kind = "preset", fetchJson = subsonicJson } = {},
) {
  if (offset === null || offset === undefined) return null;
  return {
    kind,
    cursor: offset,
    async fetchNext(cursor) {
      const { method, params } = build(cursor, pageSize);
      try {
        const tracks = listOf(await fetchJson(method, params), "songs.song");
        return { tracks, cursor: tracks.length < pageSize ? null : cursor + tracks.length };
      } catch (error) {
        console.warn("Could not load the next page of a song query", error);
        return { tracks: [], cursor, failed: true };
      }
    },
  };
}

/**
 * One page of the listen history (`getSpotifyHistory`), newest first.
 *
 * @param {number} offset
 * @param {number} pageSize
 * @param {string} auth - The `authParams` query string.
 * @param {{fetchImpl?: typeof fetch}} [options]
 * @returns {Promise<{entries: object[], hasMore: boolean}>}
 * @throws {Error} When the server does not answer 2xx.
 */
export async function fetchHistoryPage(offset, pageSize, auth, { fetchImpl = fetch } = {}) {
  const response = await fetchImpl(
    restUrl(`/rest/getSpotifyHistory?offset=${offset}&count=${pageSize}&${auth}`),
  );
  if (!response.ok) throw new Error("Network response was not ok");
  const data = await response.json();
  const node = data?.["subsonic-response"]?.history;
  const raw = node?.entry ?? [];
  const entries = Array.isArray(raw) ? raw : [raw];
  return { entries, hasMore: hasMoreResults(node?.moreResults, entries.length, pageSize) };
}

/**
 * The listen history as a continuation. A song listened to twice is one row in the queue:
 * `extendQueue` never appends an id the queue already holds.
 *
 * @param {number|null} offset - Where the history continues; null when it does not.
 * @param {{pageSize?: number, fetchImpl?: typeof fetch}} [options]
 * @returns {object|null}
 */
export function historyContinuation(offset, { pageSize = 50, fetchImpl = fetch } = {}) {
  if (offset === null || offset === undefined) return null;
  return {
    kind: "history",
    cursor: offset,
    async fetchNext(cursor) {
      try {
        const page = await fetchHistoryPage(cursor, pageSize, get(authParams), { fetchImpl });
        return {
          tracks: page.entries,
          cursor: page.hasMore ? cursor + page.entries.length : null,
        };
      } catch (error) {
        console.warn("Could not load the next page of the history", error);
        return { tracks: [], cursor, failed: true };
      }
    },
  };
}
