/**
 * Helpers for the artist curation tab.
 *
 * Same shape as `genreCuration.js`: the pure data lives here -- which states and
 * proposal kinds exist, what a row will do to a tag, how a page of proposals turns
 * into decisions -- so the component only renders. The validation duplicates what
 * `/api/rules/artists/decide` enforces, so a disabled button and a rejected request
 * agree.
 */

import { formatDateTime } from "../i18n/index.js";

export const WHITE = "white";
export const BLACK = "black";
export const UNKNOWN = "unknown";

/** The filter tabs, in the order a curator works through them. */
export const STATE_FILTERS = [
  { id: UNKNOWN, labelKey: "management.artists.filterUnknown" },
  { id: WHITE, labelKey: "management.artists.filterWhite" },
  { id: BLACK, labelKey: "management.artists.filterBlack" },
  { id: "all", labelKey: "management.artists.filterAll" },
];

/**
 * What the last analysis proposed, as a filter over the queue. `null` is "everything".
 * `keep` and `split` exist in the analyzer but never reach the page: a kept name is
 * one that is already approved, and segmentation is off.
 */
export const PROPOSAL_FILTERS = [
  { id: null, labelKey: "management.artists.proposalAny" },
  { id: "reject", labelKey: "management.artists.proposalReject" },
  { id: "rewrite", labelKey: "management.artists.proposalRewrite" },
  { id: "unknown", labelKey: "management.artists.proposalNone" },
];

export const PAGE_SIZE = 100;

/**
 * What the tagger will do with this name, in words -- the i18n key and its
 * variables, so the component renders it in the interface language.
 *
 * A correction wins over the state, like it does for genres: a black row with a
 * canonical name is rewritten, not dropped.
 *
 * @param {Object} row
 * @returns {{key: string, vars?: Object}}
 */
export function describeOutcome(row) {
  if (row.canonical_name) {
    return { key: "management.artists.outcomeRewrite", vars: { target: row.canonical_name } };
  }
  if (row.state === WHITE) return { key: "management.artists.outcomeKeep" };
  if (row.state === BLACK) return { key: "management.artists.outcomeDrop" };
  return { key: "management.artists.outcomeUndecided" };
}

/**
 * The proposal on a row, in words, or null when the analysis had nothing to say
 * (no run yet, or a name it could not place).
 *
 * @param {Object} row
 * @returns {{key: string, vars?: Object}|null}
 */
export function describeProposal(row) {
  switch (row.proposal_kind) {
    case "reject":
      return { key: "management.artists.proposeReject" };
    case "rewrite":
    case "split":
      return {
        key: "management.artists.proposeRewrite",
        vars: { target: row.proposal_target || "" },
      };
    default:
      return null;
  }
}

/**
 * Validate a decision and build the request body for it.
 *
 * @param {Object} options
 * @param {string[]} options.names
 * @param {string} options.state
 * @param {string} [options.canonicalName]
 * @returns {{valid: boolean, error: string|null, payload?: Object}} `error` is an i18n key.
 */
export function buildDecision({ names, state, canonicalName = "" }) {
  const cleaned = [];
  for (const raw of names || []) {
    const name = String(raw ?? "").trim();
    if (name && !cleaned.includes(name)) cleaned.push(name);
  }
  if (cleaned.length === 0) return { valid: false, error: "management.artists.errorNoNames" };
  if (state !== WHITE && state !== BLACK) {
    return { valid: false, error: "management.artists.errorState" };
  }
  const canonical = String(canonicalName ?? "").trim();
  if (canonical && state === WHITE) {
    return { valid: false, error: "management.artists.errorApproveWithCorrection" };
  }
  if (canonical && cleaned.some((name) => name.toLowerCase() === canonical.toLowerCase())) {
    return { valid: false, error: "management.artists.errorSelfCorrection" };
  }
  return {
    valid: true,
    error: null,
    payload: { names: cleaned, state, canonical_name: canonical || null },
  };
}

/**
 * Turn the proposals on a set of rows into as few decide calls as possible.
 *
 * A `reject` proposal is a rejection; a `rewrite` is a rejection with the proposed
 * target as its correction, grouped per target so every variant of one artist is
 * one call. Rows with no usable proposal are left out and reported, so the page can
 * say "12 applied, 3 had nothing to apply" rather than silently doing less.
 *
 * @param {Object[]} rows
 * @returns {{decisions: Array<{names: string[], state: string, canonical_name: string|null}>, skipped: string[]}}
 */
export function planFromProposals(rows) {
  const rejects = [];
  const rewrites = new Map();
  const skipped = [];
  for (const row of rows || []) {
    if (row.proposal_kind === "reject") {
      rejects.push(row.name);
    } else if (
      (row.proposal_kind === "rewrite" || row.proposal_kind === "split") &&
      row.proposal_target
    ) {
      const target = row.proposal_target;
      if (!rewrites.has(target)) rewrites.set(target, []);
      rewrites.get(target).push(row.name);
    } else {
      skipped.push(row.name);
    }
  }
  const decisions = [];
  if (rejects.length) decisions.push({ names: rejects, state: BLACK, canonical_name: null });
  for (const [target, names] of rewrites) {
    decisions.push({ names, state: BLACK, canonical_name: target });
  }
  return { decisions, skipped };
}

/**
 * Human-readable provenance line for a decided row: who and when, or null while
 * nothing was decided.
 *
 * @param {Object} row
 * @returns {{when: string, by: string|null}|null}
 */
export function describeDecision(row) {
  if (!row.decided_at) return null;
  const when = formatDateTime(row.decided_at);
  return { when, by: row.decided_by || null };
}

/**
 * The page a `total` and an `offset` put the reader on, one-based, plus the last one.
 *
 * @param {number} total
 * @param {number} offset
 * @param {number} [pageSize]
 * @returns {{page: number, pages: number}}
 */
export function pageOf(total, offset, pageSize = PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil((Number(total) || 0) / pageSize));
  const page = Math.min(pages, Math.floor((Number(offset) || 0) / pageSize) + 1);
  return { page, pages };
}
