import { get } from "svelte/store";
import { authParams, currentTrack, playlist, queueContinuation } from "./store.js";

/**
 * A queue started from a paged list tops itself up before it runs out.
 *
 * Generalises what the feeds had since docs/designs/feed-length/ (bug report 122) to every list
 * that plays as a queue and has more than its first page: the songs list with any sort or filter,
 * a genre or label, search results, an artist, a preset, the history
 * (docs/designs/list-continuation/, issue #100).
 *
 * The list's source hands `startQueue` a **continuation** -- `{kind, cursor, fetchNext}` -- and
 * this module is the only thing that advances it:
 *
 * - `kind` names the source, for logging and tests (`songs`, `feed`, `preset`, ...);
 * - `cursor` is wherever the source continues, opaque here; null means it has no more;
 * - `fetchNext(cursor, {queue})` resolves to `{tracks, cursor, failed?}` and never throws: a failure
 *   comes back as `failed` with the cursor it was given. It sees the queue so a source that folds
 *   song versions together can do that against what is already queued.
 *
 * Once the current track is within `EXTEND_WHEN_LEFT` of the end, the next page is fetched and
 * appended to `playlist`. The native shell follows `playlist` the same way it follows "add to
 * queue", so the web player and the app both get it from here.
 */

/** How close to the end of the queue the next page is fetched. */
export const EXTEND_WHEN_LEFT = 3;

/**
 * How many pages one top-up may ask for when every page turns out to be tracks the queue already
 * holds -- a list re-sorted between pages, a feed rebuilt within the hour. The same rule the
 * Android Auto feed continuation follows (`FeedQueueContinuation.kt`).
 */
export const MAX_PAGES_PER_TOP_UP = 3;

/** The top-up in flight, so a burst of track changes asks the server once. */
let pending = null;

/**
 * The continuation `startQueue` should record, or null when there is none to record.
 *
 * A continuation whose cursor is already null (the page had loaded the whole list before the
 * listener pressed play) is not recorded: the queue then shows no "end of list" line for a list
 * that never continued, exactly like an album.
 *
 * @param {object|null|undefined} continuation
 * @returns {object|null}
 */
export function acceptContinuation(continuation) {
  if (!continuation || typeof continuation.fetchNext !== "function") return null;
  if (continuation.cursor === null || continuation.cursor === undefined) return null;
  return { ...continuation, exhausted: false };
}

/**
 * Appends the list's next page when the queue is about to run out.
 *
 * Does nothing -- and costs no request -- when the queue did not come from a paged list, the list
 * has no more, the current track is not near the end, or a top-up is already running. A failed
 * request keeps the continuation, so the next track change tries again; a page that says "no more"
 * marks it `exhausted`, which the queue shows as "Einde van de lijst". A queue replaced while the
 * page was loading is left alone.
 *
 * Only songs not already in the queue are appended (by id), in the order the source hands them out,
 * so a list that shifted between pages never plays a track twice.
 *
 * `force` is the queue's own "Meer laden": the listener asks for the next page now, wherever the
 * current track is -- or with nothing playing at all.
 *
 * @param {{force?: boolean}} [options]
 * @returns {Promise<boolean>} Whether anything was appended.
 */
export async function extendQueue({ force = false } = {}) {
  const continuation = get(queueContinuation);
  if (!continuation || continuation.exhausted || continuation.cursor == null || pending)
    return false;
  if (!get(authParams)) return false;

  const queue = get(playlist);
  const current = get(currentTrack);
  const index = queue.findIndex((track) => String(track.id) === String(current?.id));
  if (!force && (index < 0 || queue.length - 1 - index >= EXTEND_WHEN_LEFT)) return false;

  pending = (async () => {
    let cursor = continuation.cursor;
    let fresh = [];
    for (let asked = 0; asked < MAX_PAGES_PER_TOP_UP && cursor != null; asked++) {
      const page = await continuation.fetchNext(cursor, { queue: get(playlist) });
      if (get(queueContinuation) !== continuation) return false;
      if (!page || page.failed) {
        // Pages of nothing but repeats before this one still moved the cursor on; keep that, so
        // the retry does not fetch them again.
        if (cursor !== continuation.cursor) queueContinuation.set({ ...continuation, cursor });
        return false;
      }
      cursor = page.cursor ?? null;
      const have = new Set(get(playlist).map((track) => String(track.id)));
      for (const track of page.tracks ?? []) {
        const id = String(track.id);
        if (have.has(id)) continue;
        have.add(id);
        fresh.push(track);
      }
      if (fresh.length > 0) break;
    }
    queueContinuation.set(
      cursor == null
        ? { ...continuation, cursor: null, exhausted: true }
        : { ...continuation, cursor },
    );
    if (fresh.length > 0) playlist.update((tracks) => [...tracks, ...fresh]);
    return fresh.length > 0;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}

/**
 * A continuation over the rest of a list that is already in memory -- a memories year shows 50 of
 * its songs and loads the others with a tap, but has all of them from the one request.
 *
 * @param {Array<object>} rest - What the page does not show yet, in its order.
 * @param {{pageSize?: number, kind?: string}} [options]
 * @returns {object|null} Null when there is no rest.
 */
export function arrayContinuation(rest, { pageSize = 50, kind = "local" } = {}) {
  if (!Array.isArray(rest) || rest.length === 0) return null;
  const all = [...rest];
  return {
    kind,
    cursor: 0,
    async fetchNext(cursor) {
      const start = Number(cursor) || 0;
      const end = start + pageSize;
      return { tracks: all.slice(start, end), cursor: end < all.length ? end : null };
    },
  };
}
