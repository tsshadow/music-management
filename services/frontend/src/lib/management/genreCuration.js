/**
 * Helpers for the genre curation tab.
 *
 * Every genre the tagger has ever seen carries an explicit state: white (keep),
 * black (drop) or unknown (nobody decided yet). This module holds the parts that
 * are pure data — which states exist, what a decision means, and what a given row
 * will do to a tag — so the component only has to render them.
 */

import { get } from "svelte/store";

import { formatDateTime, t } from "../i18n/index.js";

export const WHITE = "white";
export const BLACK = "black";
export const UNKNOWN = "unknown";

/** The filter tabs, in the order a curator works through them. */
export const STATE_FILTERS = [
  { id: UNKNOWN, labelKey: "management.genres.filterUnknown" },
  { id: WHITE, labelKey: "management.genres.filterWhite" },
  { id: BLACK, labelKey: "management.genres.filterBlack" },
  { id: "all", labelKey: "management.genres.filterAll" },
];

/**
 * Casing-, accent- and punctuation-insensitive key for a genre name.
 *
 * Deliberately the same rule as `GenreRulesHelper.normalize` on the backend, so
 * the search box groups names exactly like the tagger does: 'HARDSTYLE' and
 * 'Hardstyle' are one genre, 'hard style' is a different one.
 */
export function normalizeGenre(name) {
  return (name || "")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
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
    return get(t)("management.genres.outcomeReplaced", {
      targets: targets.map((target) => target.name).join(" + "),
    });
  }
  if (row.state === WHITE) return get(t)("management.genres.outcomeKeep");
  if (row.state === BLACK) return get(t)("management.genres.outcomeDrop");
  return get(t)("management.genres.outcomeUndecided");
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
    return {
      valid: false,
      error: get(t)("management.genres.errorState", { white: WHITE, black: BLACK }),
    };
  }
  const targets = [];
  for (const raw of canonicalIds || []) {
    if (raw === "" || raw === null || raw === undefined) continue;
    const target = Number(raw);
    if (target === Number(genreId)) {
      return { valid: false, error: get(t)("management.genres.errorSelfCorrection") };
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
    .sort((a, b) => a.name.localeCompare(b.name, "nl"));
}

/** Human-readable provenance line for a decided genre. */
export function describeDecision(row) {
  if (!row.decided_at) return get(t)("management.genres.notDecided");
  const when = formatDateTime(row.decided_at);
  return row.decided_by
    ? get(t)("management.artists.decidedByAt", { when, by: row.decided_by })
    : when;
}

/**
 * What the last analysis proposed, as a filter over the queue. `null` is
 * "everything". `keep` exists in the analyzer but never reaches the queue: a
 * kept name is one that is already approved.
 */
export const PROPOSAL_FILTERS = [
  { id: null, labelKey: "management.genres.proposalAny" },
  { id: "rewrite", labelKey: "management.genres.proposalRewrite" },
  { id: "split", labelKey: "management.genres.proposalSplit" },
  { id: "reject", labelKey: "management.genres.proposalReject" },
  { id: "unknown", labelKey: "management.genres.proposalNone" },
];

/**
 * Advice below this confidence is shown but not applied in bulk: a name that
 * merely "resembles no known genre" (50) is a hunch, and a page of hunches
 * applied with one click is how a real genre ends up rejected.
 */
export const BULK_CONFIDENCE_FLOOR = 60;

/**
 * The proposal on a row, in words -- the i18n key and its variables -- or null
 * when the analysis had nothing to say (no run yet, or a name it could not place).
 *
 * @param {Object} row
 * @returns {{key: string, vars?: Object}|null}
 */
export function describeProposal(row) {
  const proposal = row?.proposal;
  if (!proposal) return null;
  const targets = (proposal.targets || []).map((target) => target.name).join(" + ");
  switch (proposal.kind) {
    case "reject":
      return { key: "management.genres.proposeReject" };
    case "rewrite":
    case "split":
      return targets
        ? { key: "management.genres.proposeRewrite", vars: { target: targets } }
        : null;
    case "keep":
      return { key: "management.genres.proposeKeep" };
    default:
      return null;
  }
}

/**
 * The decision a proposal amounts to, in the shape `buildDecision` takes, or null
 * when there is nothing to apply. A rewrite or split is a rejection with targets,
 * which is the same thing the page's "corrigeren" dialog produces; a rejection is
 * a plain rejection; a keep is an approval.
 *
 * @param {Object} row
 * @returns {{genreId: number, state: string, canonicalIds: number[]}|null}
 */
export function decisionFromProposal(row) {
  const proposal = row?.proposal;
  if (!proposal) return null;
  const ids = (proposal.targets || []).map((target) => Number(target.id));
  switch (proposal.kind) {
    case "reject":
      return { genreId: row.id, state: BLACK, canonicalIds: [] };
    case "rewrite":
    case "split":
      return ids.length ? { genreId: row.id, state: BLACK, canonicalIds: ids } : null;
    case "keep":
      return { genreId: row.id, state: WHITE, canonicalIds: [] };
    default:
      return null;
  }
}

/**
 * Which rows on a page the bulk button would apply: those with a usable
 * proposal at or above the confidence floor. The rest are reported, so the page
 * can say "12 applied, 3 left alone" rather than silently doing less.
 *
 * @param {Object[]} rows
 * @param {number} [floor]
 * @returns {{applicable: Object[], skipped: Object[]}}
 */
export function planFromProposals(rows, floor = BULK_CONFIDENCE_FLOOR) {
  const applicable = [];
  const skipped = [];
  for (const row of rows || []) {
    const decision = decisionFromProposal(row);
    if (decision && (row.proposal?.confidence ?? 0) >= floor) {
      applicable.push(row);
    } else {
      skipped.push(row);
    }
  }
  return { applicable, skipped };
}
