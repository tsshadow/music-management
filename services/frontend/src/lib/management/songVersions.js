/**
 * Helpers for the Versions page in Beheer (docs/designs/song-versions/).
 *
 * Every song with more than one version is listed with the version MuMa plays. The
 * curator can pick another one (a pin), hand the choice back to the ranking, or accept
 * a choice the last rescore changed. The ranking itself lives on the server; this
 * module only builds requests and labels.
 */

/** The sort orders the list offers, in the order the select shows them. */
export const SORTS = ["versions", "changed", "title"];

/** How many songs one page holds. */
export const PAGE_SIZE = 50;

/**
 * The query string for one page of the list.
 *
 * @param {{q?: string, sort?: string, changedOnly?: boolean, page?: number, pageSize?: number}} params
 * @returns {string}
 */
export function curationQuery({
  q = "",
  sort = "versions",
  changedOnly = false,
  page = 1,
  pageSize = PAGE_SIZE,
} = {}) {
  const query = new URLSearchParams();
  const needle = q.trim();
  if (needle) query.set("q", needle);
  query.set("sort", SORTS.includes(sort) ? sort : "versions");
  if (changedOnly) query.set("changed_only", "true");
  query.set("page", String(Math.max(1, page)));
  query.set("page_size", String(pageSize));
  return query.toString();
}

/**
 * The number of pages a total fills, never less than one.
 *
 * @param {number} total
 * @param {number} [pageSize]
 */
export function pageCount(total, pageSize = PAGE_SIZE) {
  return Math.max(1, Math.ceil((total || 0) / pageSize));
}

/**
 * A short format label: "FLAC", "MP3 320", "M4A 256". The bitrate is left off for
 * lossless files, where it says nothing about quality.
 *
 * @param {{format?: string|null, bitrate_kbps?: number|null}} version
 */
export function formatLabel(version) {
  const format = (version?.format || "").toUpperCase();
  if (!format) return "";
  if (["FLAC", "WAV", "AIFF", "ALAC"].includes(format)) return format;
  const kbps = version?.bitrate_kbps;
  if (!kbps) return format;
  // Derived from file size and duration, so it reads a few kbps high; snap to the
  // encoder settings a curator recognises.
  const common = [320, 256, 192, 160, 128, 96];
  const snapped = common.find((rate) => Math.abs(kbps - rate) <= 12);
  return `${format} ${snapped ?? kbps}`;
}

/**
 * Whether a song's automatic choice was changed by the last rescore and not yet reviewed.
 *
 * @param {{canonical_changed_at?: string|null}} song
 */
export function isChanged(song) {
  return Boolean(song?.canonical_changed_at);
}

/**
 * One row per track: the API returns a track once per file, and a pin is per track.
 * The first file of a track is kept, which is its best-scored row.
 *
 * @param {Array<{track_id: number}>} versions
 */
export function uniqueTracks(versions) {
  const seen = new Set();
  return (versions || []).filter((version) => {
    if (seen.has(version.track_id)) return false;
    seen.add(version.track_id);
    return true;
  });
}

async function readJson(response) {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // No JSON body; the status says enough.
    }
    throw new Error(detail);
  }
  return response.json();
}

/**
 * The API calls the page makes. `getHeaders` is the management page's header builder.
 *
 * @param {string} apiBase
 * @param {() => Record<string, string>} getHeaders
 */
export function songVersionsApi(apiBase, getHeaders) {
  const post = (path, body) =>
    fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: { ...getHeaders(), "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(readJson);

  return {
    /** One page of songs with several versions. */
    list: (params) =>
      fetch(`${apiBase}/api/songs/curation?${curationQuery(params)}`, {
        headers: getHeaders(),
      }).then(readJson),
    /** The ranking in force and the rescore counts. */
    ranking: () => fetch(`${apiBase}/api/songs/ranking`, { headers: getHeaders() }).then(readJson),
    /** One song with all its versions. */
    song: (workId) =>
      fetch(`${apiBase}/api/songs/${workId}`, { headers: getHeaders() }).then(readJson),
    /** Pin a version as best; null returns the choice to the ranking. */
    pin: (workId, trackId) => post(`/api/songs/${workId}/pin`, { track_id: trackId }),
    /** Accept what the rescore chose. */
    dismissChange: (workId) => post(`/api/songs/${workId}/dismiss-change`),
  };
}
