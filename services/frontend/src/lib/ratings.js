/**
 * The one place a track's rating is written, and the one place every view reads it back from.
 *
 * Before this module the track list, the player bar, Now Playing, the details sheet and car mode
 * each kept their own copy of "the rating I last set": rating a track in one of them left the
 * others showing the old stars until the page reloaded. Now every view asks {@link ratingOf} with
 * the value of {@link ratings}, and every write goes through {@link setRating} or
 * {@link clearRating}, so one tap repaints all of them at once.
 *
 * Semantics (see `docs/designs/ratings-scrobbling/`): 1-5 stars, 5 is favourite, and 1 never means
 * "delete". Clearing a rating is its own action -- Subsonic `setRating` with `rating=0`, which LMS
 * forwards to MuMa as `rating_removed` -- and only {@link clearRating} sends it.
 */
import { get, writable } from "svelte/store";
import { authParams, currentTrack, restUrl } from "./store.js";
import { subsonicError } from "./utils.js";
import { notify } from "./notifications.js";
import { t } from "./i18n/index.js";
import { logAction } from "./diagnosticsLog.js";
import { offline } from "./subsonic.js";
import { platform as defaultPlatform } from "./platform/index.js";

/** The highest rating; also what "favourite" means. */
export const MAX_RATING = 5;

/**
 * Ratings written in this session, keyed by track id, `0` for a cleared one. A track missing from
 * the map shows whatever the server sent with it (`track.userRating`).
 *
 * @type {import('svelte/store').Writable<Record<string, number>>}
 */
export const ratings = writable({});

/**
 * Per track, how many writes have been started. A failed write only rolls back when no newer write
 * for the same track started after it; otherwise two quick taps whose first one fails would undo
 * the second.
 *
 * @type {Map<string, number>}
 */
const generations = new Map();

/**
 * Tracks whose rating went into the phone's queue this session. A later rating of the same track
 * goes there too, even online, so the queue cannot send an older value after a newer direct
 * write: the queue keeps the last rating per track (docs/designs/offline-followups/).
 *
 * @type {Set<string>}
 */
const queuedOnPhone = new Set();

/** HTTP answers of a proxy whose server behind it is down: the server was not reached. */
const SERVER_DOWN_STATUSES = new Set([502, 503, 504]);

/**
 * Hands a rating to the phone's durable queue (`platform.storage.queueRating`).
 *
 * @param {object} platform
 * @param {string} id
 * @param {number} value
 * @returns {Promise<boolean>} False when there is no queue (a browser, an older APK) or it failed.
 */
async function queueOnPhone(platform, id, value) {
  try {
    const queued = (await platform?.storage?.queueRating?.(id, value)) === true;
    if (queued) queuedOnPhone.add(id);
    return queued;
  } catch (error) {
    console.warn("Could not queue the rating on the phone", error);
    return false;
  }
}

/**
 * The rating to show for a track.
 *
 * @param {Record<string, number>} map - The current value of {@link ratings}.
 * @param {{id?: string|number, userRating?: number}|null|undefined} track
 * @returns {number} 0 when unrated.
 */
export function ratingOf(map, track) {
  if (!track) return 0;
  const own = map[String(track.id)];
  if (own !== undefined) return own;
  return track.userRating || 0;
}

/**
 * What is on screen for a track right now, when the caller did not say: the session's own write,
 * else the track object it passed, else the current track if it is that one.
 *
 * @param {string} id
 * @param {{userRating?: number}|undefined} track
 * @returns {number}
 */
function shownFor(id, track) {
  if (track) return ratingOf(get(ratings), { ...track, id });
  const playing = get(currentTrack);
  return ratingOf(get(ratings), {
    id,
    userRating: playing && String(playing.id) === id ? playing.userRating : 0,
  });
}

/**
 * Puts a rating on screen everywhere: the shared map, and the `currentTrack` store when it holds
 * the same track (the native session, the car screen and a reload all read `userRating` from there).
 *
 * @param {string} id
 * @param {number} value
 */
function show(id, value) {
  ratings.update((map) => ({ ...map, [id]: value }));
  currentTrack.update((current) =>
    current && String(current.id) === id && current.userRating !== value
      ? { ...current, userRating: value }
      : current,
  );
}

/**
 * Sends one value to the server, optimistically: the new value is shown before the request goes
 * out and put back to `previous` if the server refuses or cannot be reached.
 *
 * In the app, a rating that cannot reach the server is not lost: in offline mode, or when the
 * request never got an answer from the server (a network error, a proxy's 502/503/504), it goes
 * to the phone's durable rating queue and stays on screen. A refusal by the server still rolls
 * back. A browser has no queue and rolls back as before.
 *
 * @param {string|number} trackId
 * @param {number} value - 0 clears.
 * @param {object} [options]
 * @param {number} [options.previous] - What to roll back to; defaults to what is shown now.
 * @param {object} [options.track] - A plain track object to keep in step (`userRating`), for the
 *   callers whose list is not reactive state.
 * @param {typeof fetch} [options.fetchImpl] - Injected by the tests.
 * @param {object} [options.platform] - Injected by the tests.
 * @returns {Promise<boolean>} Whether the server stored it, or the phone queued it.
 */
async function write(trackId, value, options = {}) {
  const id = String(trackId);
  const { track, fetchImpl = globalThis.fetch, platform = defaultPlatform } = options;
  const previous = options.previous ?? shownFor(id, track);
  const generation = (generations.get(id) ?? 0) + 1;
  generations.set(id, generation);
  logAction(value === 0 ? "rating.clear" : "rating.set", { trackId: id, rating: value });

  show(id, value);
  if (track) track.userRating = value;

  if ((get(offline) || queuedOnPhone.has(id)) && (await queueOnPhone(platform, id, value))) {
    if (get(offline)) notify.info(get(t)("notify.ratingQueued"));
    return true;
  }

  let reached = false;
  try {
    const response = await fetchImpl(
      restUrl(`/rest/setRating?id=${encodeURIComponent(id)}&rating=${value}&${get(authParams)}`),
    );
    reached = !SERVER_DOWN_STATUSES.has(response?.status);
    // Subsonic reports its own errors (a throttled login, an id it cannot parse, a failed write)
    // in the body with HTTP 200, so the status in the body is the only thing that says whether
    // the rating was stored.
    const failure = await subsonicError(response);
    if (failure) throw new Error(failure.message);
    return true;
  } catch (e) {
    if (!reached && (await queueOnPhone(platform, id, value))) {
      notify.info(get(t)("notify.ratingQueued"));
      return true;
    }
    console.error("Failed to update rating:", e);
    if (generations.get(id) === generation) {
      show(id, previous);
      if (track) track.userRating = previous;
    }
    notify.error(get(t)("notify.ratingFailed"), { detail: e.message });
    return false;
  }
}

/**
 * Rates a track 1-5.
 *
 * @param {string|number} trackId
 * @param {number} value - 1 to 5; anything else is refused without a request.
 * @param {object} [options] - See `write`.
 * @returns {Promise<boolean>}
 */
export function setRating(trackId, value, options = {}) {
  if (!Number.isInteger(value) || value < 1 || value > MAX_RATING) {
    return Promise.reject(new RangeError(`rating must be 1-${MAX_RATING}, got ${value}`));
  }
  return write(trackId, value, options);
}

/**
 * Removes a track's rating (LMS sends MuMa `rating_removed`).
 *
 * @param {string|number} trackId
 * @param {object} [options] - See `write`.
 * @returns {Promise<boolean>}
 */
export function clearRating(trackId, options = {}) {
  return write(trackId, 0, options);
}

/**
 * What a tap on star `star` does in every rating row: sets that many stars, or -- when the track
 * already has exactly that many -- clears the rating. The toggle is a separate, explicit clear;
 * tapping one star on an unrated track rates it 1, it never deletes anything.
 *
 * @param {{id: string|number, userRating?: number}} track
 * @param {number} star - 1 to 5.
 * @param {object} [options] - See `write`.
 * @returns {Promise<boolean>}
 */
export function tapStar(track, star, options = {}) {
  const current = ratingOf(get(ratings), track);
  const opts = { track, previous: current, ...options };
  return current === star ? clearRating(track.id, opts) : setRating(track.id, star, opts);
}

/** Forgets every rating written in this session; for a logout and for the tests. */
export function resetRatings() {
  ratings.set({});
  generations.clear();
  queuedOnPhone.clear();
}
