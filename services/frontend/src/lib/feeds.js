/**
 * The personalized feeds: the release radar and the daily mix.
 *
 * Two calls, in this order and never the other way round. MuMa ranks the feed and knows its
 * tracks by file path; LMS knows them by id, and `getSongsByPath` is the only thing that joins
 * the two. Neither side can do it alone -- MuMa has the listening history and the genre model,
 * LMS has the ids, the cover art and the stream.
 *
 * **The order MuMa returns is the whole product**: a quota per genre so a small share still
 * appears, a cap per artist, release date descending. Nothing here re-sorts it, and nothing
 * matches the paths back up afterwards -- `getSongsByPath` answers in the order it was asked and
 * simply leaves out what this server does not have, so a shorter answer is already the ranking
 * minus the gaps.
 */

import { apiBase, fetchMumaJson, restUrl } from "./mumaApi.js";

/** The slugs MuMa's API spells. */
export const RELEASE_RADAR = "release-radar";
export const DAILY_MIX = "daily-mix";

/**
 * A feed's tracks as LMS songs, ready for the queue.
 *
 * Returns an empty array for every kind of nothing -- an unbuilt taste profile, a week with no
 * releases, an unreachable server. The caller cannot tell them apart and does not need to: all
 * three mean there is nothing to show.
 *
 * @param {string} slug - `release-radar` or `daily-mix`.
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
 * The library-relative paths MuMa picked, in its order.
 *
 * `library_path` and not `file_path`: the absolute one is MuMa's own scan mount and names a file
 * LMS does not have.
 */
async function feedPaths(slug, limit) {
  const query = limit ? `?limit=${encodeURIComponent(limit)}` : "";
  try {
    const feed = await fetchMumaJson(`${apiBase()}/api/feeds/${encodeURIComponent(slug)}${query}`);
    const tracks = Array.isArray(feed?.tracks) ? feed.tracks : [];
    return tracks
      .map((track) => track.library_path)
      .filter((path) => typeof path === "string" && path.length > 0);
  } catch (err) {
    // The slug is a separate argument rather than interpolated into the message: semgrep's
    // unsafe-formatstring reads a non-literal inside a console template as a forgeable log line,
    // and it is right that the message itself should be a constant.
    console.error("Failed to load feed:", slug, err);
    return [];
  }
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
