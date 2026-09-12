/**
 * What the Downloads screen has to work out for itself.
 *
 * Kept out of the component because all of it is arithmetic over a list, and
 * because two of the three answers here are estimates whose reasoning has to be
 * written down somewhere a reader will find it.
 */

/**
 * The songs/sets boundary, in seconds. The same ten minutes the whole app uses;
 * `Dashboard` sends `minDuration=10` / `maxDuration=10` for it.
 */
export const SET_SECONDS = 600;

/**
 * The bitrate a size is estimated at when the library did not report one, in
 * kilobits per second.
 *
 * 320 rather than an average: an estimate that is too low is the one that
 * hurts. Somebody who confirms "1,2 GB" and gets 1,1 GB shrugs; somebody who
 * confirms "600 MB" and fills their phone does not.
 */
export const ASSUMED_BITRATE_KBPS = 320;

/**
 * How big a track is, and whether that is known or guessed.
 *
 * LMS answers `getSpotifyTracks` with `size` (bytes) and `bitRate` (kbps) per
 * entry, so the exact figure is usually there. It is missing from
 * `platform.storage.list()` entirely -- the Kotlin `list()` reports id, title,
 * artist, album, duration and state and no byte count -- which is why every
 * row on the Downloads screen is an estimate while the same row in a track
 * list is not.
 *
 * @param {{size?: number|string, bitRate?: number|string, duration?: number|string}} track
 * @returns {{bytes: number, estimated: boolean}} `bytes` is 0 when even a guess
 *   is impossible, which is a length of zero and nothing to show.
 */
export function trackSize(track) {
  const exact = Number(track?.size);
  if (Number.isFinite(exact) && exact > 0) return { bytes: exact, estimated: false };

  const seconds = Number(track?.duration);
  if (!Number.isFinite(seconds) || seconds <= 0) return { bytes: 0, estimated: true };

  const kbps = Number(track?.bitRate);
  const rate = Number.isFinite(kbps) && kbps > 0 ? kbps : ASSUMED_BITRATE_KBPS;
  return { bytes: Math.round((rate * 1000 * seconds) / 8), estimated: true };
}

/**
 * Whether a recording is a set, and so gets the size confirmation before it is
 * downloaded and a group of its own on the Downloads screen.
 *
 * @param {{duration?: number|string}} track
 * @returns {boolean}
 */
export function isSet(track) {
  return Number(track?.duration) >= SET_SECONDS;
}

/**
 * Bytes as a short human string, in the units a phone shows.
 *
 * Decimal rather than binary (1 kB is 1000 bytes), because that is what
 * Android's own storage screen says and a listener comparing the two should
 * not find two different numbers for the same files.
 *
 * @param {number} bytes
 * @param {string} [locale] - For the decimal separator.
 * @returns {string}
 */
export function formatBytes(bytes, locale = undefined) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "0 MB";
  const units = ["B", "kB", "MB", "GB", "TB"];
  let index = 0;
  let scaled = value;
  while (scaled >= 1000 && index < units.length - 1) {
    scaled /= 1000;
    index += 1;
  }
  const decimals = index >= 2 && scaled < 100 ? 1 : 0;
  return `${scaled.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} ${units[index]}`;
}

/**
 * Groups what is on the device the way the screen shows it: one group per
 * album, and a set on its own.
 *
 * A set is its own group because grouping a two-hour recording under the album
 * it nominally belongs to buries the one row anybody came here for; the
 * functional design asks for "grouped by album (and by set)" for exactly that
 * reason. Groups come out in the order the first of their items did, so a
 * refresh does not reshuffle the screen.
 *
 * @param {Array<{id: string, title?: string, artist?: string, album?: string,
 *   duration?: number, state?: string}>} items - `platform.storage.list()`.
 * @returns {Array<{key: string, title: string, subtitle: string, isSet: boolean,
 *   bytes: number, estimated: boolean, items: Array<object>}>}
 */
export function groupDownloads(items) {
  const groups = [];
  const byKey = new Map();

  for (const item of items ?? []) {
    const set = isSet(item);
    // A set keys on its own id so two sets from one album stay apart; an
    // untitled album keys on the artist, so "no album" does not collapse
    // everybody's loose tracks into one heap.
    const key = set ? `set:${item.id}` : `album:${item.album || ""}|${item.artist || ""}`;
    let group = byKey.get(key);
    if (!group) {
      group = {
        key,
        title: (set ? item.title : item.album) || item.title || "",
        subtitle: item.artist || "",
        isSet: set,
        bytes: 0,
        estimated: false,
        items: [],
      };
      byKey.set(key, group);
      groups.push(group);
    }
    const size = trackSize(item);
    group.bytes += size.bytes;
    group.estimated = group.estimated || size.estimated;
    group.items.push(item);
  }

  return groups;
}

/**
 * The one state a group shows, which is the worst state in it.
 *
 * A group that is half downloaded is "downloading", and one with a single
 * failure is "failed" -- that is the row somebody has to act on, and rolling it
 * up to "done" because the other nine worked is how a missing track is
 * discovered in a tunnel instead of at home.
 *
 * @param {{items: Array<{state?: string}>}} group
 * @returns {'failed'|'running'|'queued'|'done'|'none'}
 */
export function groupState(group) {
  const items = group?.items ?? [];
  // A group with nothing in it is not finished, it is absent. Reading the empty
  // set as "done" would draw a tick beside a row that holds no files.
  if (!items.length) return "none";
  const states = new Set(items.map((item) => item.state ?? "none"));
  for (const state of ["failed", "running", "queued", "none"]) {
    if (states.has(state)) return state;
  }
  return "done";
}

/**
 * How far along a group is, as a percentage, for the progress bar.
 *
 * Per item rather than per byte, because the byte counts are estimates and the
 * one number that is not (`progress`, straight from `DownloadTask`) is already
 * a percentage of that item -- 0 to 100, not 0 to 1, and null whenever the
 * server did not send a content length, which reads here as "no progress yet".
 *
 * @param {{items: Array<{state?: string, progress?: number}>}} group
 * @returns {number} 0..100.
 */
export function groupProgress(group) {
  const items = group?.items ?? [];
  if (!items.length) return 0;
  const total = items.reduce((sum, item) => {
    if (item.state === "done") return sum + 100;
    const progress = Number(item.progress);
    return sum + (Number.isFinite(progress) ? Math.min(Math.max(progress, 0), 100) : 0);
  }, 0);
  return total / items.length;
}
