/**
 * Helpers for the downloader Coverage tab.
 *
 * The API hands over one snapshot per channel (held / excluded / remaining over
 * listed) plus the source totals. Filtering and sorting happen here, on the
 * client: 1.100 SoundCloud rows is a list, not a dataset.
 */

import { get } from "svelte/store";
import { t } from "../i18n/index.js";

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

export const FILTERS = ["backlog", "all", "complete", "uncounted"];
export const SORTS = ["remaining", "coverage", "name", "lastDownload"];

/** Whether a row has ever been counted by a deep pass. */
export function isCounted(row) {
  return row && row.listed !== null && row.listed !== undefined;
}

/** Keep the rows the chosen filter and search term ask for. */
export function filterAccounts(rows, filter, query = "") {
  const needle = (query || "").trim().toLowerCase();
  return (rows || []).filter((row) => {
    if (
      needle &&
      !String(row.account || "")
        .toLowerCase()
        .includes(needle)
    )
      return false;
    if (filter === "backlog") return isCounted(row) && Number(row.remaining || 0) > 0;
    if (filter === "complete") return isCounted(row) && Number(row.remaining || 0) === 0;
    if (filter === "uncounted") return !isCounted(row);
    return true;
  });
}

/**
 * Order the rows. Uncounted channels always sink to the bottom: whatever the
 * key, a row with no numbers cannot be ranked among rows that have them.
 */
export function sortAccounts(rows, sort) {
  const byName = (a, b) =>
    String(a.account).localeCompare(String(b.account), undefined, { sensitivity: "base" });
  const keyed = [...(rows || [])];
  const compare =
    {
      remaining: (a, b) => Number(b.remaining || 0) - Number(a.remaining || 0) || byName(a, b),
      coverage: (a, b) => Number(a.coverage ?? 2) - Number(b.coverage ?? 2) || byName(a, b),
      name: byName,
      lastDownload: (a, b) => {
        const left = a.last_download_at ? Date.parse(a.last_download_at) : 0;
        const right = b.last_download_at ? Date.parse(b.last_download_at) : 0;
        return right - left || byName(a, b);
      },
    }[sort] || byName;
  keyed.sort((a, b) => {
    const counted = Number(isCounted(b)) - Number(isCounted(a));
    return counted || compare(a, b);
  });
  return keyed;
}

/** `0.3` → `30%`; nothing to say → an em dash. */
export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 100)}%`;
}

/**
 * How long ago something happened, in the coarsest unit that still reads
 * honestly. Unknown stays unknown rather than becoming "just now".
 */
export function formatAge(iso, now = Date.now()) {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const elapsed = Math.max(0, now - then);
  const tr = get(t);
  if (elapsed < HOUR) return tr("management.downloaders.coverage.ageUnderHour");
  if (elapsed < DAY)
    return tr("management.downloaders.duration.hours", { count: Math.floor(elapsed / HOUR) });
  const days = Math.floor(elapsed / DAY);
  if (days < 60) return tr("management.downloaders.duration.days", { count: days });
  return tr("management.downloaders.coverage.ageMonths", { count: Math.floor(days / 30) });
}

/**
 * The three widths of the coverage bar, in percent of `listed`. They add up to
 * 100 for a counted row and to 0 for one that was never counted, so the bar
 * itself says "no data" by staying empty.
 */
export function barSegments(row) {
  const listed = Number(row?.listed || 0);
  if (!isCounted(row) || listed <= 0) return { held: 0, excluded: 0, remaining: 0 };
  const held = (Number(row.held || 0) / listed) * 100;
  const excluded = (Number(row.excluded || 0) / listed) * 100;
  return { held, excluded, remaining: Math.max(0, 100 - held - excluded) };
}

/** The write-off reasons the downloaders record that have a label of their own. */
export const REASONS = ["too_short", "too_long", "403", "failing", "failed"];

/** The label for a write-off reason in the active locale; an unknown reason shows as itself. */
export function reasonLabel(reason) {
  if (!REASONS.includes(String(reason))) return reason;
  return get(t)(`management.downloaders.coverage.reason.${reason}`);
}

/** How a deep pass can end. */
export const STATES = ["complete", "capped", "parked"];

/** The label for how a deep pass ended, in the active locale; no state means never counted. */
export function stateLabel(state) {
  if (!state) return get(t)("management.downloaders.coverage.uncounted");
  if (!STATES.includes(state)) return state;
  return get(t)(`management.downloaders.coverage.state.${state}`);
}
