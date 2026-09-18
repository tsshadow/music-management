/**
 * Helpers for the genre rule panels on the Genre Curatie page.
 *
 * Two rule tables feed the tagger a genre from something else on the track: the
 * artist (`rules_artist_genres`) and the label (`rules_label_genres`). They have
 * the same shape apart from the name column, so one panel serves both and this
 * module carries the per-kind differences plus the pure parts -- filtering,
 * sorting, validation -- so the component only renders.
 */

import { normalizeGenre } from "./genreCuration.js";

/** What differs between the two rule kinds: where the rows live and what a row calls its subject. */
export const RULE_KINDS = {
  artist: {
    id: "artist",
    rulesPath: "/api/rules/artist-genres",
    searchPath: "/api/artists",
    nameField: "artist_name",
    subjectIdField: "artist_id",
    /** The player view that edits the subject; needs the library id. */
    editView: (row) => (row.artist_id ? `artist-edit:${row.artist_id}` : null),
    labelKey: "management.genres.rulesArtist",
    subjectKey: "common.artist",
  },
  label: {
    id: "label",
    rulesPath: "/api/rules/label-genres",
    searchPath: "/api/labels",
    nameField: "label_name",
    subjectIdField: "label_id",
    editView: (row) => (row.label_name ? `label-edit:${row.label_name}` : null),
    labelKey: "management.genres.rulesLabel",
    subjectKey: "library.label",
  },
};

export const RULE_SORTS = ["name", "genre", "tracks"];

/** The parts of the Genre Curatie page, in the order a curator works through them. */
export const SECTIONS = [
  { id: "queue", labelKey: "management.genres.sectionQueue" },
  { id: "overview", labelKey: "management.genres.sectionOverview" },
  { id: "artist-rules", labelKey: "management.genres.sectionArtistRules" },
  { id: "label-rules", labelKey: "management.genres.sectionLabelRules" },
];

/** The subject of a rule row -- the artist or label name -- regardless of kind. */
export function subjectOf(kind, row) {
  return row?.[RULE_KINDS[kind].nameField] ?? "";
}

/**
 * Rows whose subject or genre matches the query, ignoring case, accents and
 * punctuation -- the same key the genre queue searches on, so the two boxes agree.
 *
 * @param {string} kind
 * @param {Object[]} rows
 * @param {string} query
 */
export function filterRules(kind, rows, query) {
  const key = normalizeGenre(query);
  if (!key) return rows || [];
  return (rows || []).filter(
    (row) =>
      normalizeGenre(subjectOf(kind, row)).includes(key) ||
      normalizeGenre(row.genre_name).includes(key),
  );
}

/**
 * Rows in the requested order. `tracks` puts the rules with the widest reach
 * first, which is where a wrong rule does the most damage; the two name orders
 * are for finding one.
 */
export function sortRules(kind, rows, sort = "name") {
  const collator = new Intl.Collator("nl", { sensitivity: "base" });
  const bySubject = (a, b) => collator.compare(subjectOf(kind, a), subjectOf(kind, b));
  const sorted = [...(rows || [])];
  switch (sort) {
    case "tracks":
      return sorted.sort(
        (a, b) => Number(b.track_count ?? 0) - Number(a.track_count ?? 0) || bySubject(a, b),
      );
    case "genre":
      return sorted.sort(
        (a, b) => collator.compare(a.genre_name ?? "", b.genre_name ?? "") || bySubject(a, b),
      );
    default:
      return sorted.sort(
        (a, b) => bySubject(a, b) || collator.compare(a.genre_name ?? "", b.genre_name ?? ""),
      );
  }
}

/** How many rules point at each genre, keyed by genre id, for the overview column. */
export function countByGenre(rows) {
  const counts = {};
  for (const row of rows || []) {
    const id = String(row.genre_id);
    counts[id] = (counts[id] || 0) + 1;
  }
  return counts;
}

/**
 * Validate a new rule and build the request body for it, so a disabled button and
 * a rejected request agree. Adding the same pair twice is refused here rather
 * than upserted quietly: the row already exists, and the API would only re-stamp
 * who made it.
 *
 * @param {string} kind
 * @param {{name: string, genreId: string|number, existing?: Object[]}} input
 * @returns {{valid: boolean, error: string|null, payload?: Object}} `error` is an i18n key.
 */
export function buildRule(kind, { name, genreId, existing = [] }) {
  const subject = String(name ?? "").trim();
  if (!subject) return { valid: false, error: "management.genres.ruleNeedsName" };
  const genre = Number(genreId);
  if (!genreId || !Number.isInteger(genre) || genre <= 0) {
    return { valid: false, error: "management.genres.ruleNeedsGenre" };
  }
  const duplicate = (existing || []).some(
    (row) =>
      subjectOf(kind, row).toLowerCase() === subject.toLowerCase() &&
      Number(row.genre_id) === genre,
  );
  if (duplicate) return { valid: false, error: "management.genres.ruleExists" };
  return {
    valid: true,
    error: null,
    payload: { [RULE_KINDS[kind].nameField]: subject, genre_id: genre },
  };
}

/** Who made a rule and when, or null for a row without provenance (the seed rules). */
export function describeRule(row) {
  if (!row?.created_at) return null;
  const when = new Date(String(row.created_at).replace(" ", "T")).toLocaleDateString("nl-NL");
  return { when, by: row.created_by || null };
}

/** Overview rows whose name or parent matches the query. */
export function filterOverview(rows, query) {
  const key = normalizeGenre(query);
  if (!key) return rows || [];
  return (rows || []).filter(
    (row) =>
      normalizeGenre(row.name).includes(key) ||
      (row.parents || []).some((parent) => normalizeGenre(parent).includes(key)),
  );
}
