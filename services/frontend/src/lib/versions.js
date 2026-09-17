import { listOf, subsonicJson } from "./subsonic.js";

/**
 * Every file of one song, from muma's version API.
 *
 * `SongView.svelte` (the full song page) and `NowPlaying.svelte` (the player's "other
 * versions" section) both need the same thing -- the LMS tracks a work id collapses to --
 * and used to each carry their own copy of the paging loop below. One copy here instead,
 * because the loop has a subtlety neither caller should have to get right twice: Subsonic
 * answers its own failures with HTTP 200 and an error in the body, and a work can hold more
 * versions than one page reports, so a caller that stops at the first page silently drops
 * files rather than showing a fault.
 *
 * @param {string|number} workId
 * @param {{max?: number}} [options] - `max` bounds how many versions this call ever returns.
 *   The song page wants the true count (leaves it at the default, comfortably above any real
 *   work), the player's continuation section wants a small taste -- it never shows more than
 *   a handful of rows, so there is no reason to fetch, or wait for, the whole list.
 * @returns {Promise<Array<object>>} Every version, in the order the server returned them.
 * @throws {Error} When the server reports anything other than success.
 */
export async function loadVersions(workId, { max = 500 } = {}) {
  // The server's own page size, independent of `max`: a `max` smaller than this (the player's
  // 6) asks for exactly that many so a small request stays small on the wire, while the song
  // page's much larger `max` still pages in this chunk rather than one giant request.
  const PAGE_SIZE = 100;
  const collected = [];
  let offset = 0;
  while (collected.length < max) {
    const data = await subsonicJson("getSpotifyTracks", {
      workId,
      count: Math.min(PAGE_SIZE, max - collected.length),
      offset,
    });
    // Subsonic answers its own failures with HTTP 200 and an error in the body, so the
    // status in the body is the only thing that says this worked.
    const payload = data?.["subsonic-response"];
    if (payload?.status !== "ok") {
      throw new Error(payload?.error?.message || "failed");
    }
    const result = listOf(data, "tracks.track");
    collected.push(...result);

    const more = payload.tracks?.moreResults;
    if (!(more === true || more === "true") || result.length === 0) break;
    offset = Number(payload.tracks?.nextOffset ?? offset + PAGE_SIZE);
  }
  return collected.slice(0, max);
}
