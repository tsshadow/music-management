/**
 * Helpers for the downloader Volledigheid tab.
 *
 * The API hands over one snapshot per channel (held / excluded / remaining over
 * listed) plus the source totals. Filtering and sorting happen here, on the
 * client: 1.100 SoundCloud rows is a list, not a dataset.
 */

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
  if (elapsed < HOUR) return "< 1 uur";
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)} uur`;
  const days = Math.floor(elapsed / DAY);
  if (days < 60) return `${days} dag${days === 1 ? "" : "en"}`;
  return `${Math.floor(days / 30)} mnd`;
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

/** Dutch labels for the write-off reasons the downloaders record. */
export const REASON_LABELS = {
  too_short: "te kort",
  too_long: "te lang",
  403: "niet beschikbaar (403)",
  failing: "mislukt, wordt herkanst",
  failed: "definitief mislukt",
};

export function reasonLabel(reason) {
  return REASON_LABELS[reason] || reason;
}

/** Dutch labels for how a deep pass ended. */
export const STATE_LABELS = {
  complete: "afgerond",
  capped: "afgekapt op het maximum",
  parked: "onderbroken",
};

export function stateLabel(state) {
  if (!state) return "nog niet geteld";
  return STATE_LABELS[state] || state;
}
