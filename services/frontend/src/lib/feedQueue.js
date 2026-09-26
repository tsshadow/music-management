import { get } from "svelte/store";
import { authParams, currentTrack, feedContinuation, playlist } from "./store.js";
import { loadFeedPage } from "./feeds.js";

/**
 * A queue started from a feed tops itself up before it runs out.
 *
 * A feed is 100 tracks by default and can continue past that ("Meer laden",
 * docs/designs/feed-length/). On the feed page that is a button; in the player
 * nobody should have to press anything, so once the current track is within
 * `EXTEND_WHEN_LEFT` of the end of a queue that `startQueue` gave a
 * `continuation`, the next page is fetched and appended to `playlist`. The
 * native shell follows `playlist` the same way it follows "add to queue", so the
 * web player and the app both get it from this one place.
 *
 * Only songs not already in the queue are appended (by id): Release Radar is
 * rebuilt hourly, so a continuation across a rebuild could otherwise hand back a
 * track the queue already holds.
 */

/** How close to the end of the queue the next page is fetched. */
export const EXTEND_WHEN_LEFT = 3;

/** The top-up in flight, so a burst of track changes asks MuMa once. */
let pending = null;

/**
 * Appends the feed's next page when the queue is about to run out.
 *
 * Does nothing -- and costs no request -- when the queue did not come from a
 * feed, the feed has no more, the current track is not near the end, or a
 * top-up is already running. A failed request keeps the continuation, so the
 * next track change tries again; a page that says "no more" drops it. A queue
 * replaced while the page was loading is left alone.
 *
 * @param {{loadPage?: typeof loadFeedPage}} [options] - `loadPage` is injected by the tests.
 * @returns {Promise<boolean>} Whether anything was appended.
 */
export async function extendFeedQueue({ loadPage = loadFeedPage } = {}) {
  const continuation = get(feedContinuation);
  if (!continuation?.nextOffset || pending) return false;
  const auth = get(authParams);
  if (!auth) return false;

  const queue = get(playlist);
  const current = get(currentTrack);
  const index = queue.findIndex((track) => String(track.id) === String(current?.id));
  if (index < 0 || queue.length - 1 - index >= EXTEND_WHEN_LEFT) return false;

  pending = (async () => {
    const page = await loadPage(continuation.slug, auth, continuation.nextOffset);
    if (get(feedContinuation) !== continuation) return false;
    if (page.failed) return false;
    const have = new Set(get(playlist).map((track) => String(track.id)));
    const fresh = page.tracks.filter((track) => !have.has(String(track.id)));
    feedContinuation.set(page.nextOffset ? { ...continuation, nextOffset: page.nextOffset } : null);
    if (fresh.length > 0) playlist.update((tracks) => [...tracks, ...fresh]);
    return fresh.length > 0;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}
