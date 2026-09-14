import { subsonicJson, listOf } from "./subsonic.js";

/**
 * The lines of a track's lyrics, or an empty array when LMS has none for it --
 * most tracks, since coverage depends on an embedded tag or a matching `.lrc`
 * file (see `ScanStepAssociateExternalLyrics.cpp` and `LyricsFileScanner.cpp`
 * in `services/music-management-server`). An empty array is also what a
 * network error or an unmatched id resolves to: nothing to show is nothing to
 * show, regardless of why, and the caller decides what "nothing" means for its
 * own layout (see `Player.svelte`, which hides the lyrics affordance entirely
 * rather than rendering a "no lyrics" placeholder for the common case).
 *
 * Goes by song id (`getLyricsBySongId`) rather than the artist/title text
 * match `getLyrics` does, because an id always resolves to exactly one track;
 * a text match can hit more than one candidate and LMS answers nothing at all
 * in that case (see `handleGetLyrics` in `MediaRetrieval.cpp`, which returns
 * lyrics only when the search finds exactly one track). `TrackList.svelte`
 * already looks lyrics up this way for the same reason -- this is the same
 * lookup, pulled out so `Player.svelte` can use it for whatever is currently
 * playing without a second implementation of the same parsing.
 *
 * @param {string|number|null|undefined} trackId
 * @param {object} [options] - Forwarded to `subsonicJson`; lets tests inject `fetchImpl`.
 * @returns {Promise<string[]>}
 */
export async function fetchLyricsLines(trackId, options = {}) {
  if (trackId === null || trackId === undefined || trackId === "") return [];
  try {
    const body = await subsonicJson("getLyricsBySongId", { id: trackId }, options);
    const structured = listOf(body, "lyricsList.structuredLyrics");
    const entry = structured[0];
    if (!entry?.line) return [];
    const lines = Array.isArray(entry.line) ? entry.line : [entry.line];
    return lines
      .map((line) => line?.value)
      .filter((value) => typeof value === "string" && value !== "");
  } catch (error) {
    console.warn("Could not fetch lyrics for track %s", trackId, error);
    return [];
  }
}
