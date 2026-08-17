/**
 * Helpers for the podcast curation tab.
 *
 * Radio shows and podcast series carry the same explicit state genres do: white
 * (tag it), black (never tag it) or unknown (nobody decided yet). The state
 * vocabulary, the summary counts and the provenance line are literally the same
 * contract, so they are re-exported from `genreCuration.js` rather than written
 * twice. What is specific to shows lives here: a show has spellings, and the
 * correction a show needs is a merge into another show rather than a rewrite.
 */

import {
  BLACK,
  STATE_FILTERS,
  UNKNOWN,
  WHITE,
  describeDecision,
  normalizeGenre as normalizeName,
  summarize
} from './genreCuration.js';

export { BLACK, STATE_FILTERS, UNKNOWN, WHITE, describeDecision, normalizeName, summarize };

/** Rows whose name or any of its spellings matches the query. */
export function filterPodcasts(rows, query) {
  const key = normalizeName(query);
  if (!key) return rows;
  return rows.filter((row) =>
    [row.name, ...(row.aliases || [])].some((name) => normalizeName(name).includes(key))
  );
}

/**
 * What the tagger will do with this show, in words.
 *
 * An undecided show is not a harmless one: it means every episode of it stays
 * unlabelled, which is the state the whole library starts in.
 */
export function describeOutcome(row) {
  if (row.state === WHITE) return 'Wordt getagd op elke aflevering';
  if (row.state === BLACK) return 'Wordt nooit getagd';
  return 'Nog geen beslissing, dus niet getagd';
}

/** The spellings other than the show's own name, which is already in the title. */
export function extraAliases(row) {
  const name = normalizeName(row.name);
  return (row.aliases || []).filter((alias) => normalizeName(alias) !== name);
}

/**
 * Validate a curation decision and build the request body for it.
 *
 * Returns `{ valid, error, payload }` rather than throwing, so the component can
 * disable the confirm button on the same check the API would reject.
 *
 * A merge carries a state as well, because the API takes one request: the state
 * is ignored server-side once a merge target is given, and the row is gone.
 */
export function buildDecision({ podcastId, state, mergeIntoId = null, host = null, station = null }) {
  if (state !== WHITE && state !== BLACK) {
    return { valid: false, error: `Ongeldige status, verwacht ${WHITE} of ${BLACK}.` };
  }
  if (mergeIntoId !== null && mergeIntoId !== '' && mergeIntoId !== undefined) {
    if (Number(mergeIntoId) === Number(podcastId)) {
      return { valid: false, error: 'Een show kan niet in zichzelf samengevoegd worden.' };
    }
    return {
      valid: true,
      error: null,
      payload: { state, merge_into_podcast_id: Number(mergeIntoId) }
    };
  }
  return {
    valid: true,
    error: null,
    payload: { state, host: host || null, station: station || null }
  };
}

/**
 * Shows a merge may point at: approved ones, never the row itself.
 *
 * Merging into an undecided show would move the spellings somewhere that is
 * still not tagged, which looks like the merge did nothing.
 */
export function mergeTargets(rows, podcastId) {
  return rows
    .filter((row) => row.state === WHITE && Number(row.id) !== Number(podcastId))
    .sort((a, b) => a.name.localeCompare(b.name, 'nl'));
}

/** Episode count line for a row, e.g. "125 afleveringen". */
export function describeEpisodes(row) {
  const count = Number(row.occurrences) || 0;
  return count === 1 ? '1 aflevering' : `${count} afleveringen`;
}
