/**
 * Pure synchronisation maths for radio mode.
 *
 * The server owns the timeline: each entry carries an absolute `started_at` in
 * server-clock seconds. A client can only place itself on that timeline if it
 * knows how far its own clock is from the server's, hence the offset
 * measurement. Everything here is deliberately side-effect free so it can be
 * tested without an audio element.
 */

/** Above this error (seconds) we jump instead of nudging. */
export const HARD_SEEK_THRESHOLD = 3.0;

/** Below this error (seconds) we leave playback alone. */
export const DEADBAND = 0.15;

/**
 * Median of (serverTime - local round-trip midpoint) over several samples.
 *
 * @param {Array<{t0: number, t1: number, serverTime: number}>} samples - all in ms.
 * @returns {number} offset in ms to add to a local timestamp to get server time.
 */
export function medianClockOffset(samples) {
  if (!samples || samples.length === 0) return 0;
  const offsets = samples
    .map((s) => s.serverTime - (s.t0 + s.t1) / 2)
    .sort((a, b) => a - b);
  const mid = Math.floor(offsets.length / 2);
  return offsets.length % 2 ? offsets[mid] : (offsets[mid - 1] + offsets[mid]) / 2;
}

/**
 * Where playback should be, in seconds into the track.
 *
 * @param {{startedAtMs: number}} entry
 * @param {number} serverNowMs - current time on the server's clock, in ms.
 * @returns {number} seconds (negative if the entry has not started yet).
 */
export function targetPosition(entry, serverNowMs) {
  return (serverNowMs - entry.startedAtMs) / 1000;
}

/**
 * Decide how to close the gap between where we are and where we should be.
 *
 * @param {number} localPos - current playback position in seconds.
 * @param {number} targetPos - desired position in seconds.
 * @returns {{action: 'none'|'rate'|'seek', rate: number, position?: number}}
 */
export function correction(localPos, targetPos) {
  const error = targetPos - localPos; // positive => we are behind
  if (Math.abs(error) > HARD_SEEK_THRESHOLD) {
    return { action: 'seek', position: targetPos, rate: 1 };
  }
  if (Math.abs(error) < DEADBAND) {
    return { action: 'none', rate: 1 };
  }
  const rate = Math.min(1.02, Math.max(0.98, 1 + error / 10));
  return { action: 'rate', rate };
}
