import { get } from "svelte/store";
import { authParams } from "./store.js";
import { loadFeedPage } from "./feeds.js";

/**
 * A feed as a list continuation (docs/designs/list-continuation/).
 *
 * A feed is 100 tracks by default and continues past that ("Meer laden",
 * docs/designs/feed-length/). This used to be the one kind of queue that topped itself up
 * (`extendFeedQueue`); the top-up is generic now (`listContinuation.js` `extendQueue`), and a feed
 * is one source of continuation pages among several. The cursor is MuMa's `next_offset`.
 *
 * Release Radar is rebuilt hourly, so a page asked for across a rebuild can hand back a track the
 * queue already holds; `extendQueue` leaves those out by id.
 *
 * @param {string} slug - The feed's slug.
 * @param {number|null} nextOffset - Where the feed continues; null or 0 when it does not.
 * @param {{loadPage?: typeof loadFeedPage}} [options] - `loadPage` is injected by the tests.
 * @returns {object|null} The continuation, or null when the feed has nothing more.
 */
export function feedContinuation(slug, nextOffset, { loadPage = loadFeedPage } = {}) {
  if (!slug || !nextOffset) return null;
  return {
    kind: "feed",
    slug,
    cursor: nextOffset,
    async fetchNext(cursor) {
      let page;
      try {
        page = await loadPage(slug, get(authParams), cursor);
      } catch (error) {
        console.warn("Could not load the next page of a feed", error);
        return { tracks: [], cursor, failed: true };
      }
      if (page.failed) return { tracks: [], cursor, failed: true };
      return { tracks: page.tracks, cursor: page.nextOffset || null };
    },
  };
}
