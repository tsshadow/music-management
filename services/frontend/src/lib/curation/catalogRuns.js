/**
 * Pure formatting behind the Catalogus section of the label edit page.
 *
 * The backend hands over a series as numbers (`absent_runs: [[287, 289]]`, `width: 4`,
 * `prefix: "DWX"`); everything that turns those back into catalogue numbers a person
 * can read or paste lives here, so it can be tested without mounting the component.
 */
import { get } from "svelte/store";

import { t } from "../i18n/index.js";

/** How many runs the section shows before it folds the rest behind "toon alles". */
export const RUNS_SHOWN = 40;

/**
 * One catalogue number written the way the series writes them: prefix, separator,
 * number zero-padded to the series' width. A number wider than the width is never
 * truncated.
 *
 * @param {{prefix: string, separator?: string, width: number}} series
 * @param {number} number
 * @returns {string}
 */
export function catid(series, number) {
  return `${series.prefix}${series.separator || ""}${String(number).padStart(series.width, "0")}`;
}

/**
 * A run as text: a lone number as itself, a stretch as `from–to` with an en dash.
 *
 * @param {{prefix: string, separator?: string, width: number}} series
 * @param {[number, number]} run
 * @returns {string}
 */
export function formatRun(series, [from, to]) {
  return from === to ? catid(series, from) : `${catid(series, from)}–${catid(series, to)}`;
}

/**
 * The runs of a series as one comma-separated line.
 *
 * @param {{prefix: string, separator?: string, width: number, absent_runs: number[][]}} series
 * @param {number[][]} [runs] - Defaults to the series' own runs; pass a slice to fold.
 * @returns {string}
 */
export function formatRuns(series, runs = series.absent_runs) {
  return runs.map((run) => formatRun(series, run)).join(", ");
}

/**
 * Every absent catalogue number of a series, one per line, each written in full.
 *
 * This is the artefact the owner searches with: `DWX0287–DWX0289` is readable, but a
 * search tool wants `DWX0287`, `DWX0288` and `DWX0289` as three separate terms.
 *
 * @param {{prefix: string, separator?: string, width: number, absent_runs: number[][]}} series
 * @returns {string}
 */
export function searchTerms(series) {
  const lines = [];
  for (const [from, to] of series.absent_runs) {
    for (let number = from; number <= to; number += 1) lines.push(catid(series, number));
  }
  return lines.join("\n");
}

/**
 * The header line of a series: `DWX · 000–2212 · 1921 van 2213 aanwezig (87%)`.
 *
 * The range is written with the series' padding so it reads like the folder names;
 * a series without a prefix (a label that numbers its releases bare) is named as such.
 *
 * @param {{prefix: string, separator?: string, width: number, min: number, max: number, present: number, coverage: number}} series
 * @returns {string}
 */
export function seriesHeader(series) {
  const translate = get(t);
  const name = series.prefix || translate("curation.noPrefix");
  const pad = (n) => String(n).padStart(series.width, "0");
  const span = series.max - series.min + 1;
  const percent = Math.round(series.coverage * 100);
  const present = translate("curation.seriesPresent", { present: series.present, span, percent });
  return `${name} · ${pad(series.min)}–${pad(series.max)} · ${present}`;
}
