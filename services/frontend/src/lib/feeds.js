/**
 * The personalized feeds: the release radar and the five daily mixes (three on the hardness
 * spectrum, plus the day's artist and label), and the classic, unfiltered daily mix the car and
 * the phone already called before the spectrum existed.
 *
 * Two calls, in this order and never the other way round. MuMa ranks the feed and knows its
 * tracks by file path; LMS knows them by id, and `getSongsByPath` is the only thing that joins
 * the two. Neither side can do it alone -- MuMa has the listening history and the genre model,
 * LMS has the ids, the cover art and the stream.
 *
 * **The order MuMa returns is the whole product**: a quota per genre so a small share still
 * appears, a cap per artist, release date descending (or, for a daily mix, a day-stable sample
 * order). Nothing here re-sorts it, and nothing matches the paths back up afterwards --
 * `getSongsByPath` answers in the order it was asked and simply leaves out what this server does
 * not have, so a shorter answer is already the ranking minus the gaps.
 */

import { apiBase, fetchMumaJson, getHeaders, restUrl } from "./mumaApi.js";

/** The slugs MuMa's API spells. */
export const RELEASE_RADAR = "release-radar";
/** The classic, unrestricted daily mix -- not one of the three spectrum bands, and not their alias. */
export const DAILY_MIX = "daily-mix";
export const DAILY_MIX_SOFT = "daily-mix-soft";
export const DAILY_MIX_MID = "daily-mix-mid";
export const DAILY_MIX_HARD = "daily-mix-hard";
export const DAILY_MIX_ARTIST = "daily-mix-artist";
export const DAILY_MIX_LABEL = "daily-mix-label";

/** The three-band spectrum, soft to hard. */
export const DAILY_MIX_BANDS = [DAILY_MIX_SOFT, DAILY_MIX_MID, DAILY_MIX_HARD];

/**
 * The five daily mixes the "Daily mixes" shelf and phone page show, in display order. The classic
 * `daily-mix` is deliberately not among them -- it stays reachable at its own `/daily-mix` route,
 * not as a sixth card, exactly as docs/designs/feeds/functional.md's "Daily mixes v2" describes.
 */
export const DAILY_MIXES = [...DAILY_MIX_BANDS, DAILY_MIX_ARTIST, DAILY_MIX_LABEL];

/**
 * "Oude hitjes": old favourites the listener plays less (docs/designs/old-hits-feed/). Not a
 * daily mix -- its own builder on the server -- but day-stable like one, so it sits on the same
 * shelf, after the five mixes.
 */
export const OLD_HITS = "old-hits";

/** Every card on the daily-mix shelf and the phone's "Daily mixes" page, in display order. */
export const SHELF_FEEDS = [...DAILY_MIXES, OLD_HITS];

/** A feed answer shaped like an error, for every kind of nothing this can fail with. */
function emptyFeed(slug) {
  return {
    slug,
    state: "error",
    tracks: [],
    title: null,
    subtitle: null,
    hardness_band: null,
    relaxed_to: null,
    filled_from_unknown: null,
  };
}

/**
 * The in-flight or resolved `GET /api/feeds` call, so a page that shows several mixes at once
 * asks MuMa for the list exactly once. A failed fetch is not cached, the same way
 * `genreTints.js` does not cache one -- MuMa being briefly unreachable should not leave the
 * session without titles until a reload.
 */
let feedsPending = null;

/**
 * Every feed this account may ask for: `[{slug, size, window_days, title, subtitle}, ...]`, all
 * seven policies including the classic `daily-mix`. Titles and subtitles come from the server, so
 * a client never invents its own copy of "Zachter" or "Middenin".
 *
 * @returns {Promise<Object[]>}
 */
export function listFeeds() {
  if (feedsPending) return feedsPending;

  feedsPending = (async () => {
    try {
      const data = await fetchMumaJson(`${apiBase()}/api/feeds`, { headers: getHeaders() });
      // A body without a list is a failure too, not "there are no feeds": caching it would
      // hide every feed for the rest of the session.
      if (!Array.isArray(data?.feeds)) throw new Error("The feeds answer holds no list");
      return data.feeds;
    } catch (err) {
      console.error("Failed to list feeds:", err);
      feedsPending = null;
      return [];
    }
  })();

  return feedsPending;
}

/** Forgets what was fetched. Tests use this; nothing in the app does. */
export function resetFeedsCache() {
  feedsPending = null;
}

/**
 * One page of a feed: MuMa's answer for `GET /api/feeds/{slug}`, tracks and all.
 *
 * Never throws -- an unreachable server or an unknown slug comes back as the same shape a caller
 * can render without a special case, `state: "error"` reading no differently to a caller than
 * `not_enough_data` or `no_matches` would.
 *
 * Without `offset` this is the head of the day's feed (the configured length, 100 by default);
 * with one it is the continuation "Meer laden" asks for, and `next_offset` in the answer says
 * where the page after it starts -- null when the feed has nothing more
 * (docs/designs/feed-length/technical.md).
 *
 * @param {string} slug
 * @param {number} [limit]
 * @param {number} [offset]
 * @returns {Promise<Object>}
 */
export async function fetchFeed(slug, limit, offset) {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  const query = params.toString() ? `?${params}` : "";
  try {
    const feed = await fetchMumaJson(`${apiBase()}/api/feeds/${encodeURIComponent(slug)}${query}`, {
      headers: getHeaders(),
    });
    return feed && typeof feed === "object" ? feed : emptyFeed(slug);
  } catch (err) {
    // The slug is a separate argument rather than interpolated into the message: semgrep's
    // unsafe-formatstring reads a non-literal inside a console template as a forgeable log line,
    // and it is right that the message itself should be a constant.
    console.error("Failed to load feed:", slug, err);
    return emptyFeed(slug);
  }
}

/**
 * The library-relative paths MuMa picked for one feed, in its order.
 *
 * `library_path` and not `file_path`: the absolute one is MuMa's own scan mount and names a file
 * LMS does not have.
 *
 * @param {string} slug
 * @param {number} [limit]
 * @returns {Promise<string[]>}
 */
export async function feedPaths(slug, limit) {
  return pathsOf(await fetchFeed(slug, limit));
}

/**
 * The most paths LMS resolves in one `getSongsByPath` call (`SongsByPath.cpp`, `maxPathCount`).
 * A feed longer than this -- `feeds_size` goes up to 200 -- is resolved in chunks, in order.
 */
export const SONGS_BY_PATH_LIMIT = 100;

/**
 * Turn one chunk of paths into songs.
 *
 * A POST rather than a GET, and not for style: a hundred paths run to several kilobytes, which is
 * well past where a request line starts meeting proxy buffer limits. The credentials stay in the
 * query string; LMS reads its parameters out of both.
 *
 * `failed` is true when LMS could not be asked or refused: the page offers a retry for exactly
 * that chunk, rather than counting its hundred paths as "not on the server".
 *
 * @param {string[]} paths - At most `SONGS_BY_PATH_LIMIT`.
 * @param {string} authParams
 * @returns {Promise<{songs: Object[], failed: boolean}>}
 */
export async function resolveFeedChunk(paths, authParams) {
  const body = new URLSearchParams();
  paths.forEach((path) => body.append("path", path));

  try {
    const response = await fetch(restUrl(`/rest/getSongsByPath.view?${authParams}`), {
      method: "POST",
      body,
    });
    if (!response.ok) throw new Error(`status ${response.status}`);

    const data = await response.json();
    const songs = data["subsonic-response"]?.songsByPath?.song ?? [];
    return { songs: Array.isArray(songs) ? songs : [songs], failed: false };
  } catch (err) {
    console.error("Failed to resolve a feed to songs:", err);
    return { songs: [], failed: true };
  }
}

/**
 * The paths cut into `SONGS_BY_PATH_LIMIT`-sized chunks, in order.
 *
 * @param {string[]} paths
 * @returns {string[][]}
 */
export function chunkPaths(paths) {
  const chunks = [];
  for (let start = 0; start < paths.length; start += SONGS_BY_PATH_LIMIT) {
    chunks.push(paths.slice(start, start + SONGS_BY_PATH_LIMIT));
  }
  return chunks;
}

/**
 * Turn paths into songs, `SONGS_BY_PATH_LIMIT` at a time, every chunk at once.
 *
 * Parallel since issue #110: `/rest` calls do not pass the serial `/muma` gate (`mumaGate.js`),
 * and a feed is at most two chunks (`feeds_size` tops out at 200), so the cost to LMS is one extra
 * request in flight, not a burst. The order of the answer is still the order of the feed: each
 * chunk keeps its index and the songs are joined by it, never by arrival. `onChunk(index, result)`
 * fires as each chunk lands, for a page that draws the rows before the rest have come back.
 *
 * @param {string[]} paths
 * @param {string} authParams
 * @param {(index: number, result: {songs: Object[], failed: boolean}) => void} [onChunk]
 * @returns {Promise<{songs: Object[], unresolved: number, failedChunks: number}>}
 */
async function resolveSongs(paths, authParams, onChunk) {
  const chunks = chunkPaths(paths);
  const results = await Promise.all(
    chunks.map(async (chunk, index) => {
      const result = await resolveFeedChunk(chunk, authParams);
      onChunk?.(index, result);
      return result;
    }),
  );
  let unresolved = 0;
  let failedChunks = 0;
  results.forEach((result, index) => {
    if (result.failed) failedChunks += 1;
    else unresolved += unresolvedCount(chunks[index], result.songs);
  });
  return { songs: results.flatMap((result) => result.songs), unresolved, failedChunks };
}

/** The library-relative paths of a feed answer, in its order, blanks left out. */
function pathsOf(feed) {
  const tracks = Array.isArray(feed?.tracks) ? feed.tracks : [];
  return tracks
    .map((track) => track.library_path)
    .filter((path) => typeof path === "string" && path.length > 0);
}

/**
 * A feed's tracks as LMS songs, ready for the queue.
 *
 * Returns an empty array for every kind of nothing -- an unbuilt taste profile, a week with no
 * releases, an unreachable server. The caller cannot tell them apart and does not need to: all
 * three mean there is nothing to show.
 *
 * @param {string} slug - Any of the seven slugs `GET /api/feeds` lists.
 * @param {string} authParams - The Subsonic credentials, already query-encoded.
 * @param {number} [limit] - Fewer tracks than the feed's own size, for a home row.
 * @returns {Promise<Object[]>}
 */
export async function loadFeed(slug, authParams, limit) {
  if (!authParams) return [];

  const paths = await feedPaths(slug, limit);
  if (paths.length === 0) return [];

  return (await resolveSongs(paths, authParams)).songs;
}

/**
 * One feed's whole page: the songs, and what MuMa said about the feed itself.
 *
 * A single `GET /api/feeds/{slug}` carries both -- the tracks and the title/subtitle/hardness
 * numbers -- so this resolves the songs from the same answer rather than asking MuMa twice.
 * `nextOffset` is where "Meer laden" continues (`loadFeedPage`), null when there is no more.
 * `unresolved` counts the paths LMS did not return a song for (bug report 122): the list is
 * shorter than MuMa's page by exactly that many, and the page says so rather than letting a
 * 100-track mix read as a 98-track one for no visible reason. It never shifts the paging --
 * `nextOffset` counts MuMa's rows, resolved or not.
 *
 * @param {string} slug
 * @param {string} authParams
 * @param {number} [limit]
 * @returns {Promise<{state: string, title: string|null, subtitle: string|null,
 *   hardnessBand: [number, number]|null, relaxedTo: (number|string|null),
 *   filledFromUnknown: number|null, nextOffset: number|null, unresolved: number,
 *   failedChunks: number, tracks: Object[]}>}
 */
export async function loadFeedDetail(slug, authParams, limit) {
  return streamFeedDetail(slug, authParams, { limit });
}

/**
 * `loadFeedDetail`, told as it happens -- the feed page's progressive load (issue #110).
 *
 * `onHeader` fires as soon as MuMa's answer is in, before a single song is resolved: the title,
 * subtitle and band line, and `chunks`, the paths cut the way they will be resolved, so the page
 * can size its skeleton. Then `onChunk(index, {songs, failed})` fires for each chunk as LMS
 * answers it, in whatever order that happens; the chunks are all asked at once. The promise
 * resolves with the same object `loadFeedDetail` returns once every chunk has settled.
 *
 * `unresolved` only counts chunks that answered: a chunk that failed is `failedChunks`, which a
 * page offers to retry (`resolveFeedChunk`) instead of reporting a hundred missing files.
 *
 * @param {string} slug
 * @param {string} authParams
 * @param {{limit?: number,
 *   onHeader?: (header: Object) => void,
 *   onChunk?: (index: number, result: {songs: Object[], failed: boolean}) => void}} [handlers]
 * @returns {ReturnType<typeof loadFeedDetail>}
 */
export async function streamFeedDetail(slug, authParams, { limit, onHeader, onChunk } = {}) {
  const feed = await fetchFeed(slug, limit);
  const paths = authParams ? pathsOf(feed) : [];
  const header = {
    state: feed.state,
    title: feed.title ?? null,
    subtitle: feed.subtitle ?? null,
    hardnessBand: feed.hardness_band ?? null,
    relaxedTo: feed.relaxed_to ?? null,
    filledFromUnknown: feed.filled_from_unknown ?? null,
    nextOffset: nextOffsetOf(feed),
  };
  onHeader?.({ ...header, chunks: chunkPaths(paths) });

  const resolved =
    paths.length > 0
      ? await resolveSongs(paths, authParams, onChunk)
      : { songs: [], unresolved: 0, failedChunks: 0 };

  return {
    ...header,
    unresolved: resolved.unresolved,
    failedChunks: resolved.failedChunks,
    tracks: resolved.songs,
  };
}

/**
 * How many of MuMa's paths LMS left out of its answer: files MuMa has scanned that this server has
 * not indexed (yet), or no longer has. Zero when nothing was asked.
 */
function unresolvedCount(paths, songs) {
  return Math.max(0, paths.length - songs.length);
}

/** `next_offset` when MuMa sent a usable one, else null. */
function nextOffsetOf(feed) {
  const next = feed?.next_offset;
  return Number.isInteger(next) && next > 0 ? next : null;
}

/**
 * The next page of a feed as LMS songs: what "Meer laden" and a feed queue running out ask for.
 *
 * `failed` separates "MuMa could not be reached" from "the feed is exhausted": a caller keeps
 * its continuation after a failure, so the next tap or the next track tries again, and drops it
 * only when the server says there is nothing more.
 *
 * @param {string} slug
 * @param {string} authParams
 * @param {number} offset - The `nextOffset` the previous page carried.
 * @returns {Promise<{tracks: Object[], nextOffset: number|null, unresolved: number, failed: boolean}>}
 */
export async function loadFeedPage(slug, authParams, offset) {
  const feed = await fetchFeed(slug, undefined, offset);
  if (feed.state === "error")
    return { tracks: [], nextOffset: offset, unresolved: 0, failed: true };
  const paths = authParams ? pathsOf(feed) : [];
  const resolved =
    paths.length > 0
      ? await resolveSongs(paths, authParams)
      : { songs: [], unresolved: 0, failedChunks: 0 };
  // LMS failing to answer is a failed page too, not a page of missing files: the caller keeps
  // its continuation and the next tap asks for the same page again.
  if (resolved.failedChunks > 0)
    return { tracks: [], nextOffset: offset, unresolved: 0, failed: true };
  return {
    tracks: resolved.songs,
    nextOffset: nextOffsetOf(feed),
    unresolved: resolved.unresolved,
    failed: false,
  };
}
