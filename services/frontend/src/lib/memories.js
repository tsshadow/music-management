/**
 * Shared helpers for the Memories feature.
 *
 * Both the Memories view and the home carousel read the same endpoint and label groups the same
 * way, so the parsing and the heading rule live here rather than in either component.
 */

import { restUrl, playlist, currentTrack, playerState } from "./store.js";

/**
 * Today as `YYYY-MM-DD` in the browser's own time zone.
 *
 * Built by hand rather than with `toISOString()`, which converts to UTC first and therefore reports
 * the wrong day for part of every evening in western time zones.
 *
 * @param {Date} [date=new Date()] - The moment to format.
 * @returns {string} The local date in `YYYY-MM-DD` form.
 */
export function localDateString(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * What the overview asks for per year.
 *
 * The server ranks a year before it truncates it and reports the year's real size alongside, so the
 * overview needs only enough songs to name three and to fill a four-cover mosaic. A few spare cover
 * the case where the best tracks share an album. Asking for the whole of every year instead turned
 * this screen into a multi-megabyte download.
 */
export const MEMORIES_TILE_SONGS = 12;

/** What a single year's page asks for: all of it, up to what the server will hand out. */
export const MEMORIES_YEAR_SONGS = 1000;

/**
 * The request URL for one day's memories.
 *
 * @param {string} authParams - The query string that carries the session.
 * @param {Object} [options] - What to ask for.
 * @param {string} [options.date] - The local date to ask about; today when left out.
 * @param {number|string} [options.year] - One year rather than every year.
 * @returns {string} The URL to fetch.
 */
export function memoriesUrl(authParams, { date = localDateString(), year } = {}) {
  const maxPerYear = year ? MEMORIES_YEAR_SONGS : MEMORIES_TILE_SONGS;
  const yearParam = year ? `year=${year}&` : "";

  return `/rest/getMemories?date=${date}&maxPerYear=${maxPerYear}&${yearParam}${authParams}`;
}

/**
 * Normalises a `getMemories` response into year groups.
 *
 * The Subsonic JSON encoding collapses a single-element array into a bare object, so both the
 * `memory` list and each group's `song` list are coerced back into arrays here.
 *
 * @param {Object} data - The parsed JSON body of the response.
 * @returns {Array<{year: number, yearsAgo: number, exact: boolean, songs: Object[]}>} The groups.
 */
export function parseMemoryGroups(data) {
  const raw = data?.["subsonic-response"]?.memories?.memory;
  if (!raw) return [];

  const list = Array.isArray(raw) ? raw : [raw];

  return list.map((group) => ({
    ...group,
    songs: Array.isArray(group.song) ? group.song : group.song ? [group.song] : [],
  }));
}

/**
 * The translation key and variables for a group's heading.
 *
 * A group only claims "today" when it actually contains a release from today's date; one that
 * exists purely because of the surrounding-days window says "this week" instead.
 *
 * @param {{exact: boolean, yearsAgo: number}} group - The group to label.
 * @returns {{key: string, vars: {count: number}}} Key and interpolation variables for `$t`.
 */
export function memoryHeading(group) {
  return {
    key: group.exact ? "memories.today" : "memories.thisWeek",
    vars: { count: group.yearsAgo },
  };
}

/**
 * How many tracks a year holds.
 *
 * The server counts the whole year in `songCount`; the songs in hand are only the page it sent, and
 * a screen that counts those claims every busy year is exactly as big as the limit that truncated
 * it. A server too old to report a count leaves the caller counting what it was given.
 *
 * @param {{songCount?: number|string, songs?: Object[]}} group - A parsed memory group.
 * @returns {number} The year's size.
 */
export function memoryCount(group) {
  return Number(group?.songCount) || group?.songs?.length || 0;
}

/** How many of a year's songs a tile names, and how many covers its collage holds. */
const TILE_TOP_COUNT = 3;
const TILE_COVER_COUNT = 4;

/**
 * A year's songs, most loved first.
 *
 * The library has no popularity figure of its own, so the ranking is assembled from what every song
 * node already carries: a favourite (five stars) outranks everything, and inside that bucket -- and
 * inside the rest -- the listen count decides, with the rating settling what is left.
 *
 * Songs this cannot tell apart keep the order they arrived in, which matters more than it looks:
 * most of a memory year is neither rated nor played, and the server has already ordered exactly
 * those by how deliberate their release is. Sorting them again by title would throw that away.
 *
 * @param {Object[]} songs - The songs to rank. Not modified.
 * @returns {Object[]} A new array, best first.
 */
export function rankSongs(songs) {
  const rating = (song) => Number(song?.userRating) || 0;
  const listens = (song) => Number(song?.playCount) || 0;
  const favourite = (song) => (rating(song) >= 5 ? 1 : 0);

  return [...songs].sort(
    (a, b) => favourite(b) - favourite(a) || listens(b) - listens(a) || rating(b) - rating(a),
  );
}

/**
 * The per-year tiles the Memories overview shows.
 *
 * A tile is a summary, not a page: it keeps the year's own facts, the full track count, the three
 * most loved titles and up to four covers for the collage. Songs without cover art are skipped for
 * the collage but still counted, so a tagless track cannot punch a hole in the mosaic.
 *
 * The covers come from the server when it names any: it looks at the whole year rather than at the
 * page it sent, which matters because the tracks that rank highest are frequently the ones without
 * artwork. Falling back to the songs in hand keeps a server that names none from showing a blank
 * mosaic.
 *
 * Either way the covers are deduplicated. A year's best tracks routinely come off one album -- in a
 * real library most years do -- and four copies of the same sleeve is not a collage.
 *
 * @param {Array<{year: number, yearsAgo: number, exact: boolean, songs: Object[]}>} groups - Groups
 *   as returned by {@link parseMemoryGroups}.
 * @returns {Array<{year: number, yearsAgo: number, exact: boolean, count: number, top: Object[], covers: string[]}>}
 *   One tile per year that has songs, in the order the server sent them.
 */
export function yearTiles(groups) {
  return groups
    .filter((group) => group.songs.length > 0)
    .map((group) => {
      const ranked = rankSongs(group.songs);

      // The Subsonic JSON encoding collapses a single-element array into a bare object here too.
      const named = Array.isArray(group.cover) ? group.cover : group.cover ? [group.cover] : [];
      const coverIds =
        named.length > 0 ? named.map((cover) => cover?.id) : ranked.map((song) => song.coverArt);

      return {
        year: group.year,
        yearsAgo: group.yearsAgo,
        exact: group.exact,
        count: memoryCount(group),
        top: ranked.slice(0, TILE_TOP_COUNT),
        covers: [...new Set(coverIds.filter(Boolean))].slice(0, TILE_COVER_COUNT),
      };
    });
}

/**
 * Plays one year of memories, in the order the server sent it.
 *
 * A tile only holds a short summary page (`MEMORIES_TILE_SONGS`), so playing a year fetches the
 * whole year first: pressing play on 2024 should queue 2024, not the handful of tracks that
 * happened to fit the tile. Falls back to the summary already in memory when that fetch fails, so
 * the play button never does nothing. Shared by `MemoriesView.svelte`'s grid and `PhoneHome.svelte`'s
 * home-screen year row, which each hold their own copy of the summary groups.
 *
 * @param {number|string} year - The year to play.
 * @param {Array<{year: number, songs: Object[]}>} groups - The summary groups currently in memory,
 *   used only as a fallback.
 * @param {string} authParams - The query string that carries the session.
 * @returns {Promise<void>}
 */
export async function playMemoryYear(year, groups, authParams) {
  let songs = [];
  try {
    const response = await fetch(restUrl(memoriesUrl(authParams, { year })));
    if (response.ok) {
      const data = await response.json();
      songs = parseMemoryGroups(data).find((g) => String(g.year) === String(year))?.songs ?? [];
    }
  } catch (e) {
    console.error("Failed to load a year of memories:", e);
  }

  // A failed fetch still has the summary's own page to fall back on, which is better than a play
  // button that does nothing.
  if (songs.length === 0) {
    songs = groups.find((candidate) => candidate.year === year)?.songs ?? [];
  }
  if (songs.length === 0) return;

  playlist.set(songs);
  currentTrack.set(songs[0]);
  playerState.update((s) => ({ ...s, playing: true }));
}
