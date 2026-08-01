/**
 * Helpers for the genre curation tab.
 *
 * Every genre the tagger has ever seen carries an explicit state: white (keep),
 * black (drop) or unknown (nobody decided yet). This module holds the parts that
 * are pure data — which states exist, what a decision means, and what a given row
 * will do to a tag — so the component only has to render them.
 */

export const WHITE = 'white';
export const BLACK = 'black';
export const UNKNOWN = 'unknown';

/** The filter tabs, in the order a curator works through them. */
export const STATE_FILTERS = [
  { id: UNKNOWN, label: 'Te beoordelen' },
  { id: WHITE, label: 'Goedgekeurd' },
  { id: BLACK, label: 'Afgekeurd' },
  { id: 'all', label: 'Alles' }
];

/**
 * Casing-, accent- and punctuation-insensitive key for a genre name.
 *
 * Deliberately the same rule as `GenreRulesHelper.normalize` on the backend, so
 * the search box groups names exactly like the tagger does: 'HARDSTYLE' and
 * 'Hardstyle' are one genre, 'hard style' is a different one.
 */
export function normalizeGenre(name) {
  return (name || '')
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

/** Rows whose name matches the query, ignoring case, accents and punctuation. */
export function filterGenres(rows, query) {
  const key = normalizeGenre(query);
  if (!key) return rows;
  return rows.filter((row) => normalizeGenre(row.name).includes(key));
}

/** Count how many genres sit in each state, for the header badges. */
export function summarize(rows) {
  const counts = { [WHITE]: 0, [BLACK]: 0, [UNKNOWN]: 0, total: rows.length };
  for (const row of rows) {
    if (row.state in counts) counts[row.state] += 1;
  }
  return counts;
}

/**
 * What the tagger will do with this genre, in words.
 *
 * A correction wins over the state: a row with a `canonical_id` is rewritten
 * whether it is white or black, which is how 'uptempo' ends up saved as
 * 'Uptempo Hardcore'.
 */
export function describeOutcome(row) {
  const targets = row.canonical_targets || [];
  if (targets.length) {
    return `Wordt vervangen door ${targets.map((target) => target.name).join(' + ')}`;
  }
  if (row.state === WHITE) return 'Blijft staan';
  if (row.state === BLACK) return 'Wordt verwijderd';
  return 'Blijft in het bestand, wordt niet opgeslagen';
}

/**
 * Validate a curation decision and build the request body for it.
 *
 * Returns `{ valid, error, payload }` rather than throwing, so the component can
 * disable the confirm button on the same check the API would reject.
 *
 * Several targets are allowed, which is how a contraction is expressed:
 * 'Upterror' becomes 'Uptempo Hardcore' plus 'Terror'.
 */
export function buildDecision({ genreId, state, canonicalIds = [] }) {
  if (state !== WHITE && state !== BLACK) {
    return { valid: false, error: `Ongeldige status, verwacht ${WHITE} of ${BLACK}.` };
  }
  const targets = [];
  for (const raw of canonicalIds || []) {
    if (raw === '' || raw === null || raw === undefined) continue;
    const target = Number(raw);
    if (target === Number(genreId)) {
      return { valid: false, error: 'Een genre kan niet naar zichzelf corrigeren.' };
    }
    if (!targets.includes(target)) targets.push(target);
  }
  return { valid: true, error: null, payload: { state, canonical_ids: targets } };
}

/**
 * Genres that a correction may point at: approved ones, never the row itself.
 *
 * Pointing a correction at a black or undecided genre would rewrite one problem
 * into another, so those are not offered.
 */
export function correctionTargets(rows, genreId) {
  return rows
    .filter((row) => row.state === WHITE && Number(row.id) !== Number(genreId))
    .sort((a, b) => a.name.localeCompare(b.name, 'nl'));
}

/** Human-readable provenance line for a decided genre. */
export function describeDecision(row) {
  if (!row.decided_at) return 'Nog niet beoordeeld';
  const when = new Date(row.decided_at.replace(' ', 'T')).toLocaleString('nl-NL');
  return row.decided_by ? `${when} door ${row.decided_by}` : when;
}
