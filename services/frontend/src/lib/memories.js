/**
 * Shared helpers for the Memories feature.
 *
 * Both the Memories view and the home carousel read the same endpoint and label groups the same
 * way, so the parsing and the heading rule live here rather than in either component.
 */

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
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * The page size the Memories screens ask for.
 *
 * The server's own default keeps a group short enough for a carousel, but a year page shows the
 * whole year and a tile reports its size, so both ask for the server's maximum instead.
 */
export const MEMORIES_MAX_PER_YEAR = 200;

/**
 * The request URL for one day's memories.
 *
 * @param {string} authParams - The query string that carries the session.
 * @param {string} [date] - The local date to ask about; today when left out.
 * @returns {string} The URL to fetch.
 */
export function memoriesUrl(authParams, date = localDateString()) {
  return `/rest/getMemories?date=${date}&maxPerYear=${MEMORIES_MAX_PER_YEAR}&${authParams}`;
}

/**
 * Normalises a `/rest/getMemories` response into year groups.
 *
 * The Subsonic JSON encoding collapses a single-element array into a bare object, so both the
 * `memory` list and each group's `song` list are coerced back into arrays here.
 *
 * @param {Object} data - The parsed JSON body of the response.
 * @returns {Array<{year: number, yearsAgo: number, exact: boolean, songs: Object[]}>} The groups.
 */
export function parseMemoryGroups(data) {
  const raw = data?.['subsonic-response']?.memories?.memory;
  if (!raw) return [];

  const list = Array.isArray(raw) ? raw : [raw];

  return list.map((group) => ({
    ...group,
    songs: Array.isArray(group.song) ? group.song : group.song ? [group.song] : []
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
    key: group.exact ? 'memories.today' : 'memories.thisWeek',
    vars: { count: group.yearsAgo }
  };
}

/** How many of a year's songs a tile names, and how many covers its collage holds. */
const TILE_TOP_COUNT = 3;
const TILE_COVER_COUNT = 4;

/**
 * A year's songs, most loved first.
 *
 * The library has no popularity figure of its own, so the ranking is assembled from what every song
 * node already carries: a favourite (five stars) outranks everything, and inside that bucket -- and
 * inside the rest -- the listen count decides. Rating and title only settle ties, which keeps the
 * order stable between renders of the same data.
 *
 * @param {Object[]} songs - The songs to rank. Not modified.
 * @returns {Object[]} A new array, best first.
 */
export function rankSongs(songs) {
  const rating = (song) => Number(song?.userRating) || 0;
  const listens = (song) => Number(song?.playCount) || 0;
  const favourite = (song) => (rating(song) >= 5 ? 1 : 0);

  return [...songs].sort(
    (a, b) =>
      favourite(b) - favourite(a) ||
      listens(b) - listens(a) ||
      rating(b) - rating(a) ||
      String(a.title ?? '').localeCompare(String(b.title ?? ''))
  );
}

/**
 * The per-year tiles the Memories overview shows.
 *
 * A tile is a summary, not a page: it keeps the year's own facts, the full track count, the three
 * most loved titles and up to four covers for the collage. Songs without cover art are skipped for
 * the collage but still counted, so a tagless track cannot punch a hole in the mosaic.
 *
 * The covers are also deduplicated. A year's best tracks routinely come off one album -- in a real
 * library most years do -- and four copies of the same sleeve is not a collage.
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

      return {
        year: group.year,
        yearsAgo: group.yearsAgo,
        exact: group.exact,
        count: group.songs.length,
        top: ranked.slice(0, TILE_TOP_COUNT),
        covers: [...new Set(ranked.map((song) => song.coverArt).filter(Boolean))].slice(
          0,
          TILE_COVER_COUNT
        )
      };
    });
}
