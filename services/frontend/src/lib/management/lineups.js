/**
 * Helpers for the lineups tab: the pure data between the file list, the editor and
 * the match report.
 */

/**
 * The lineup files grouped by festival, in the order the list came (alphabetical).
 *
 * @param {Array<{id: string, festival: string, year: string|null, stage: string|null, artists: number}>} lineups
 * @returns {Array<{festival: string, lineups: Array}>}
 */
export function groupByFestival(lineups) {
  const groups = new Map();
  for (const lineup of lineups || []) {
    if (!groups.has(lineup.festival)) groups.set(lineup.festival, []);
    groups.get(lineup.festival).push(lineup);
  }
  return [...groups].map(([festival, entries]) => ({ festival, lineups: entries }));
}

/**
 * The editor fields for a lineup id: `Defqon.1/2014/RED` is festival, year and stage;
 * a flat `Intents 2025` is a festival on its own.
 *
 * @param {string} id
 * @returns {{festival: string, year: string, stage: string}}
 */
export function fieldsFromId(id) {
  const [festival = "", year = "", stage = ""] = String(id ?? "").split("/");
  return { festival, year, stage };
}

/**
 * Validate the editor and build the request body for it.
 *
 * @param {{festival: string, year: string, stage: string, text: string}} form
 * @returns {{valid: boolean, error: string|null, payload?: Object}} `error` is an i18n key.
 */
export function buildLineup(form) {
  const festival = String(form?.festival ?? "").trim();
  const year = String(form?.year ?? "").trim();
  const stage = String(form?.stage ?? "").trim();
  const text = String(form?.text ?? "");
  if (!festival) return { valid: false, error: "management.lineups.errorFestival" };
  if (year && !/^\d{4}$/.test(year)) return { valid: false, error: "management.lineups.errorYear" };
  if (stage && !year) return { valid: false, error: "management.lineups.errorStageWithoutYear" };
  if (!text.trim()) return { valid: false, error: "management.lineups.errorEmpty" };
  return {
    valid: true,
    error: null,
    payload: { festival, year: year ? Number(year) : null, stage: stage || null, text },
  };
}

/**
 * The editor text with one unmatched name replaced by the spelling the library holds,
 * so a suggestion is one click rather than a retype.
 *
 * @param {string} text
 * @param {string} name - The line as typed.
 * @param {string} replacement - The library's spelling.
 * @returns {string}
 */
export function replaceName(text, name, replacement) {
  return String(text ?? "")
    .split("\n")
    .map((line) =>
      line.trim().toLowerCase() === String(name).trim().toLowerCase() ? replacement : line,
    )
    .join("\n");
}
