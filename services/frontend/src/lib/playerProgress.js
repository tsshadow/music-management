/**
 * The playable length of the current track, in seconds.
 *
 * `HTMLMediaElement.duration` is the honest answer whenever the browser has
 * worked one out, but it is `NaN` until the metadata lands and `Infinity` for a
 * stream that arrives chunked without a `Content-Length` -- which is what a
 * transcoding stream hands the LG TV browser. Both values turn every
 * `progress / duration` into `NaN` and pin the bar at zero width forever. The
 * track metadata already carries the length, so fall back to it.
 *
 * @param {number} elementDuration - `audioElement.duration`.
 * @param {number} trackDuration - The length the server reported for the track.
 * @returns {number} A usable length in seconds, or 0 when neither source has one.
 */
export function resolveDuration(elementDuration, trackDuration) {
  if (Number.isFinite(elementDuration) && elementDuration > 0) return elementDuration;
  if (Number.isFinite(trackDuration) && trackDuration > 0) return trackDuration;
  return 0;
}

/**
 * How far the progress bar is filled, as a percentage.
 *
 * Written straight into a `width:` style, so it may never come out `NaN`: the
 * browser drops the whole declaration and the bar keeps whatever width it had.
 *
 * @param {number} progress - Position in seconds.
 * @param {number} duration - Track length in seconds.
 * @returns {number} A number between 0 and 100.
 */
export function progressPercent(progress, duration) {
  if (!Number.isFinite(progress) || !Number.isFinite(duration) || duration <= 0) return 0;
  return Math.max(0, Math.min(100, (progress / duration) * 100));
}

/**
 * Formats seconds into a "M:SS" string, shared between the mini player and the
 * full-screen Now Playing view so a track's elapsed/total time reads the same
 * everywhere.
 *
 * @param {number} seconds - Time in seconds.
 * @returns {string} Formatted time string.
 */
export function formatTime(seconds) {
  // `Infinity` as well as `NaN`: an endless stream reports one, and it would
  // render as "Infinity:NaN".
  if (!Number.isFinite(seconds)) return "0:00";
  const min = Math.floor(seconds / 60);
  const sec = Math.floor(seconds % 60);
  return `${min}:${sec < 10 ? "0" : ""}${sec}`;
}
