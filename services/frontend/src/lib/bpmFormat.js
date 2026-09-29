/**
 * The BPM pill's text, on its own so `TrackList` can show it without pulling in the BPM
 * browse's API code (`bpm.js`).
 */

/**
 * How a track's BPM is written in a row: "150" for a measurement, "≈152" for a coarse value.
 *
 * @param {{bpm: number, approximate?: boolean}|null|undefined} info
 * @returns {string}
 */
export function formatBpm(info) {
  if (!info || !Number.isFinite(info.bpm)) return "";
  const rounded = Math.round(info.bpm);
  return info.approximate ? `≈${rounded}` : String(rounded);
}
