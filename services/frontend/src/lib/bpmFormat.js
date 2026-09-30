/**
 * The BPM pill's text, on its own so `TrackList` can show it without pulling in the BPM
 * browse's API code (`bpm.js`).
 */

/**
 * How a track's BPM is written anywhere it is shown: "150" for a measurement, "≈152" for a
 * coarse value. Every place that prints the effective BPM goes through here -- the BPM
 * browse's pill, the library table and inspector, the track details sheet (issue #141) -- so
 * the marker means the same everywhere. The API sends `bpm` as a number (or a numeric
 * string) and `approximate` as a boolean or the database's 0/1.
 *
 * @param {{bpm: number|string|null|undefined, approximate?: boolean|number|null}|null|undefined} info
 * @returns {string} "" when there is no usable BPM
 */
export function formatBpm(info) {
  if (!info || info.bpm === null || info.bpm === undefined || info.bpm === "") return "";
  const value = Number(info.bpm);
  if (!Number.isFinite(value) || value <= 0) return "";
  const rounded = Math.round(value);
  return info.approximate ? `≈${rounded}` : String(rounded);
}
