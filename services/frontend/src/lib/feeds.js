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
      return Array.isArray(data?.feeds) ? data.feeds : [];
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
 * One feed, whole: MuMa's answer for `GET /api/feeds/{slug}`, tracks and all.
 *
 * Never throws -- an unreachable server or an unknown slug comes back as the same shape a caller
 * can render without a special case, `state: "error"` reading no differently to a caller than
 * `not_enough_data` or `no_matches` would.
 *
 * @param {string} slug
 * @param {number} [limit]
 * @returns {Promise<Object>}
 */
export async function fetchFeed(slug, limit) {
  const query = limit ? `?limit=${encodeURIComponent(limit)}` : "";
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
  const feed = await fetchFeed(slug, limit);
  const tracks = Array.isArray(feed?.tracks) ? feed.tracks : [];
  return tracks
    .map((track) => track.library_path)
    .filter((path) => typeof path === "string" && path.length > 0);
}

/**
 * Turn paths into songs.
 *
 * A POST rather than a GET, and not for style: thirty paths run to several kilobytes, which is
 * around where a request line starts meeting proxy buffer limits. The credentials stay in the
 * query string; LMS reads its parameters out of both.
 */
async function resolveSongs(paths, authParams) {
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
    return Array.isArray(songs) ? songs : [songs];
  } catch (err) {
    console.error("Failed to resolve a feed to songs:", err);
    return [];
  }
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

  return resolveSongs(paths, authParams);
}

/**
 * One feed's whole page: the songs, and what MuMa said about the feed itself.
 *
 * A single `GET /api/feeds/{slug}` carries both -- the tracks and the title/subtitle/hardness
 * numbers -- so this resolves the songs from the same answer rather than asking MuMa twice.
 *
 * @param {string} slug
 * @param {string} authParams
 * @param {number} [limit]
 * @returns {Promise<{state: string, title: string|null, subtitle: string|null,
 *   hardnessBand: [number, number]|null, relaxedTo: (number|string|null),
 *   filledFromUnknown: number|null, tracks: Object[]}>}
 */
export async function loadFeedDetail(slug, authParams, limit) {
  const feed = await fetchFeed(slug, limit);
  const tracks = Array.isArray(feed?.tracks) ? feed.tracks : [];
  const paths = tracks
    .map((track) => track.library_path)
    .filter((path) => typeof path === "string" && path.length > 0);
  const songs = authParams && paths.length > 0 ? await resolveSongs(paths, authParams) : [];

  return {
    state: feed.state,
    title: feed.title ?? null,
    subtitle: feed.subtitle ?? null,
    hardnessBand: feed.hardness_band ?? null,
    relaxedTo: feed.relaxed_to ?? null,
    filledFromUnknown: feed.filled_from_unknown ?? null,
    tracks: songs,
  };
}
