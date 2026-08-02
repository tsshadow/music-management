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
