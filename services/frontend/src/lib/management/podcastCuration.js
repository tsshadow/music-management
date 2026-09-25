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

import { get } from "svelte/store";

import { t } from "../i18n/index.js";
import {
  BLACK,
  STATE_FILTERS,
  UNKNOWN,
  WHITE,
  describeDecision,
  normalizeGenre as normalizeName,
  summarize,
} from "./genreCuration.js";

export { BLACK, STATE_FILTERS, UNKNOWN, WHITE, describeDecision, normalizeName, summarize };

/** Rows whose name or any of its spellings matches the query. */
export function filterPodcasts(rows, query) {
  const key = normalizeName(query);
  if (!key) return rows;
  return rows.filter((row) =>
    [row.name, ...(row.aliases || [])].some((name) => normalizeName(name).includes(key)),
  );
}

/**
 * What the tagger will do with this show, in words.
 *
 * An undecided show is not a harmless one: it means every episode of it stays
 * unlabelled, which is the state the whole library starts in.
 */
export function describeOutcome(row) {
  if (row.state === WHITE) return get(t)("management.podcasts.outcomeTagged");
  if (row.state === BLACK) return get(t)("management.podcasts.outcomeNever");
  return get(t)("management.podcasts.outcomeUndecided");
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
export function buildDecision({
  podcastId,
  state,
  mergeIntoId = null,
  host = null,
  station = null,
}) {
  if (state !== WHITE && state !== BLACK) {
    return {
      valid: false,
      error: get(t)("management.genres.errorState", { white: WHITE, black: BLACK }),
    };
  }
  if (mergeIntoId !== null && mergeIntoId !== "" && mergeIntoId !== undefined) {
    if (Number(mergeIntoId) === Number(podcastId)) {
      return { valid: false, error: get(t)("management.podcasts.errorSelfMerge") };
    }
    return {
      valid: true,
      error: null,
      payload: { state, merge_into_podcast_id: Number(mergeIntoId) },
    };
  }
  return {
    valid: true,
    error: null,
    payload: { state, host: host || null, station: station || null },
  };
}

/**
 * Shortest normalized name or spelling that may be stored.
 *
 * Mirrors `MINIMUM_SHOW_KEY_LENGTH` in the management router. Matching is a
 * substring test on the title and the path together, so a two-letter spelling
 * would tag unrelated files; the check lives here as well so the button is
 * disabled before the request rather than after the 400.
 */
export const MINIMUM_KEY_LENGTH = 4;

/**
 * Validate a new show name and build the request body for it.
 *
 * The name is what ends up in the PODCAST tag on every episode, and it doubles
 * as a spelling the tagger matches on, which is why it has the same floor an
 * alias has.
 *
 * @param {string} name
 * @returns {{valid: boolean, error: string|null, payload?: {name: string}}}
 */
export function buildRename(name) {
  const trimmed = (name || "").trim();
  const key = normalizeName(trimmed);
  if (!key) return { valid: false, error: get(t)("management.podcasts.errorNameEmpty") };
  if (key.length < MINIMUM_KEY_LENGTH) {
    return {
      valid: false,
      error: get(t)("management.podcasts.errorNameShort", { min: MINIMUM_KEY_LENGTH }),
    };
  }
  return { valid: true, error: null, payload: { name: trimmed } };
}

/**
 * Validate a spelling and build the request body for it.
 *
 * @param {string} alias
 * @returns {{valid: boolean, error: string|null, payload?: {alias: string}}}
 */
export function buildAlias(alias) {
  const trimmed = (alias || "").trim();
  const key = normalizeName(trimmed);
  if (!key) return { valid: false, error: get(t)("management.podcasts.errorAliasEmpty") };
  if (key.length < MINIMUM_KEY_LENGTH) {
    return {
      valid: false,
      error: get(t)("management.podcasts.errorAliasShort", { min: MINIMUM_KEY_LENGTH }),
    };
  }
  return { valid: true, error: null, payload: { alias: trimmed } };
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
    .sort((a, b) => a.name.localeCompare(b.name, "nl"));
}

/** Episode count line for a row, e.g. "125 afleveringen". */
export function describeEpisodes(row) {
  const count = Number(row.occurrences) || 0;
  return get(t)("management.podcasts.episodeCount", { count });
}
