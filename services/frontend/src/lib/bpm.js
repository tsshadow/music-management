/**
 * Browse by BPM: MuMa's `/api/library/bpm` endpoints, and turning their tracks into songs.
 *
 * MuMa knows every track's effective BPM (docs/designs/bpm-browse/technical.md); LMS knows how
 * to play them. So the page asks MuMa which tracks sit at a tempo -- each with its
 * `library_path` -- and resolves those paths to songs with `getSongsByPath`, exactly as the feeds
 * do (`feeds.js`). The BPM itself rides along on each song as `mumaBpm`, which `TrackList` shows
 * as a small pill.
 *
 * Most tempos today come from an old analyzer that could only produce a coarse set of values
 * (152, 156.6, 161.5 ...), so those are marked `approximate` and shown as "≈152". The default
 * tolerance (±2, from the server) is what lets "150" find the tracks that analyzer rounded to 152.
 */

import { apiBase, fetchMumaJson, getHeaders } from "./mumaApi.js";
import { chunkPaths, resolveFeedChunk } from "./feeds.js";

export { formatBpm } from "./bpmFormat.js";

/** The tempos offered as one-tap chips: where the collection's genres actually sit. */
export const QUICK_BPMS = [128, 140, 150, 155, 160, 165, 175, 190, 200, 210, 230];

/** The tolerances the page offers; the server's default is added when it is not one of these. */
export const TOLERANCES = [0.5, 1, 2, 3, 5];

/** How many tracks one page asks for. */
export const PAGE_SIZE = 100;

/** The confidence the "Betrouwbaar" switch asks for. */
export const RELIABLE = "medium";

/** The histogram's span on the page: everything the collection plays below speedcore. */
export const HISTOGRAM_RANGE = { from: 60, to: 260 };

/**
 * The query string for one request, empty values left out.
 *
 * @param {Object} params
 * @returns {string}
 */
export function bpmQuery(params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

/**
 * The request parameters for a selection: a picked tempo with its tolerance, or a range.
 *
 * @param {{bpm?: number|null, tol?: number|null, from?: number|null, to?: number|null,
 *   reliable?: boolean, genre?: string|null}} selection
 * @returns {Object|null} null when nothing is picked yet.
 */
export function selectionParams(selection) {
  const common = {
    min_confidence: selection.reliable ? RELIABLE : null,
    genre: selection.genre || null,
  };
  if (Number.isFinite(selection.bpm)) {
    return {
      bpm: selection.bpm,
      tol: Number.isFinite(selection.tol) ? selection.tol : null,
      ...common,
    };
  }
  if (Number.isFinite(selection.from) || Number.isFinite(selection.to)) {
    return {
      bpm_from: Number.isFinite(selection.from) ? selection.from : null,
      bpm_to: Number.isFinite(selection.to) ? selection.to : null,
      ...common,
    };
  }
  return null;
}

/**
 * A number from a text field, or null when it is empty or not a plausible tempo.
 *
 * @param {string|number|null|undefined} value
 * @returns {number|null}
 */
export function parseBpm(value) {
  const text = String(value ?? "")
    .trim()
    .replace(",", ".");
  if (text === "") return null;
  const number = Number(text);
  return Number.isFinite(number) && number >= 40 && number <= 500 ? number : null;
}

/**
 * The per-track BPM facts MuMa sent, in the shape `TrackList` reads from `song.mumaBpm`.
 *
 * @param {Object} track - One entry of MuMa's `tracks`.
 * @returns {{bpm: number, source: string, confidence: string, folded: boolean, approximate: boolean}}
 */
export function bpmInfo(track) {
  return {
    bpm: track.bpm,
    source: track.bpm_source,
    confidence: track.bpm_confidence,
    folded: Boolean(track.bpm_folded),
    approximate: Boolean(track.bpm_approximate),
  };
}

/**
 * Attach MuMa's BPM to the songs LMS returned, by path.
 *
 * LMS's song `path` is relative to its library root, which is what MuMa's `library_path` is too.
 * A song whose path does not match any (a second library root) keeps its place without a pill.
 *
 * @param {Object[]} songs
 * @param {Object[]} tracks - MuMa's tracks for the same paths.
 * @returns {Object[]}
 */
export function withBpm(songs, tracks) {
  const byPath = new Map(tracks.map((track) => [track.library_path, bpmInfo(track)]));
  return songs.map((song) => {
    const info = byPath.get(song.path);
    return info ? { ...song, mumaBpm: info } : song;
  });
}

/**
 * One page of tracks from MuMa. Throws on a network error or a refusal.
 *
 * @param {Object} params - From `selectionParams`.
 * @param {number} [offset]
 * @returns {Promise<Object>}
 */
export async function fetchBpmTracks(params, offset = 0) {
  const query = bpmQuery({ ...params, limit: PAGE_SIZE, offset: offset || null });
  return fetchMumaJson(`${apiBase()}/api/library/bpm/tracks?${query}`, { headers: getHeaders() });
}

/**
 * The histogram, the genre choices and the server's default tolerance.
 *
 * @param {{reliable?: boolean, genre?: string|null}} [filters]
 * @returns {Promise<Object>}
 */
export async function fetchBpmHistogram({ reliable = false, genre = null } = {}) {
  const query = bpmQuery({
    min_confidence: reliable ? RELIABLE : null,
    genre,
    bpm_from: HISTOGRAM_RANGE.from,
    bpm_to: HISTOGRAM_RANGE.to,
  });
  return fetchMumaJson(`${apiBase()}/api/library/bpm/histogram?${query}`, {
    headers: getHeaders(),
  });
}

/**
 * One page as songs ready for the queue.
 *
 * `failed` is true when MuMa or LMS could not be asked; the page keeps what it had and offers a
 * retry. `unresolved` counts MuMa's tracks LMS had no song for.
 *
 * @param {Object} params - From `selectionParams`.
 * @param {string} authParams - The Subsonic credentials, query-encoded.
 * @param {number} [offset]
 * @param {{fetchPage?: typeof fetchBpmTracks, resolve?: typeof resolveFeedChunk}} [deps] - For tests.
 * @returns {Promise<{songs: Object[], total: number, nextOffset: number|null, unresolved: number,
 *   approximate: boolean, failed: boolean}>}
 */
export async function loadBpmPage(params, authParams, offset = 0, deps = {}) {
  const fetchPage = deps.fetchPage ?? fetchBpmTracks;
  const resolve = deps.resolve ?? resolveFeedChunk;
  let body;
  try {
    body = await fetchPage(params, offset);
  } catch (error) {
    console.error("Could not load the BPM list", error);
    return {
      songs: [],
      total: 0,
      nextOffset: offset || null,
      unresolved: 0,
      approximate: false,
      failed: true,
    };
  }
  const tracks = Array.isArray(body?.tracks)
    ? body.tracks.filter((track) => track.library_path)
    : [];
  const results = await Promise.all(
    chunkPaths(tracks.map((track) => track.library_path)).map((chunk) =>
      resolve(chunk, authParams),
    ),
  );
  const failed = results.some((result) => result.failed);
  const songs = withBpm(
    results.flatMap((result) => result.songs),
    tracks,
  );
  const next = body?.next_offset;
  return {
    songs,
    total: Number(body?.total) || 0,
    nextOffset: Number.isInteger(next) && next > 0 ? next : null,
    unresolved: failed ? 0 : Math.max(0, tracks.length - songs.length),
    approximate: tracks.some((track) => track.bpm_approximate),
    failed,
  };
}

/**
 * The BPM list as a queue continuation (`listContinuation.js`): a queue started here tops itself
 * up with the next page, like a feed's does.
 *
 * @param {Object} params - From `selectionParams`.
 * @param {number|null} nextOffset
 * @param {() => string} getAuth - Reads the current Subsonic credentials.
 * @param {{loadPage?: typeof loadBpmPage}} [deps]
 * @returns {Object|null}
 */
export function bpmContinuation(params, nextOffset, getAuth, { loadPage = loadBpmPage } = {}) {
  if (!params || !nextOffset) return null;
  return {
    kind: "bpm",
    cursor: nextOffset,
    async fetchNext(cursor) {
      const page = await loadPage(params, getAuth(), cursor);
      if (page.failed) return { tracks: [], cursor, failed: true };
      return { tracks: page.songs, cursor: page.nextOffset };
    },
  };
}

/**
 * The tallest bar of a histogram, never zero.
 *
 * @param {{count: number}[]} bins
 * @returns {number}
 */
export function peakCount(bins) {
  return Math.max(1, ...bins.map((bin) => bin.count || 0));
}

/**
 * Every whole BPM from `from` to `to`, with the server's counts filled in and zeroes between,
 * so the bars stand at their tempo rather than packed together.
 *
 * @param {{bpm: number, count: number}[]} bins
 * @param {number} [from]
 * @param {number} [to]
 * @returns {{bpm: number, count: number, high: number, medium: number, low: number}[]}
 */
export function fillBins(bins, from = HISTOGRAM_RANGE.from, to = HISTOGRAM_RANGE.to) {
  const byBpm = new Map((bins || []).map((bin) => [bin.bpm, bin]));
  const out = [];
  for (let bpm = from; bpm <= to; bpm += 1) {
    out.push(byBpm.get(bpm) ?? { bpm, count: 0, high: 0, medium: 0, low: 0 });
  }
  return out;
}

/**
 * How many tracks the histogram holds within `bpm` ± `tol` -- the count a quick chip shows.
 *
 * @param {{bpm: number, count: number}[]} bins
 * @param {number} bpm
 * @param {number} tol
 * @returns {number}
 */
export function countNear(bins, bpm, tol) {
  return (bins || []).reduce(
    (sum, bin) => (Math.abs(bin.bpm - bpm) <= tol ? sum + bin.count : sum),
    0,
  );
}
