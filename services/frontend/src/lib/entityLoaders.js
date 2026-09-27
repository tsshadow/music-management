/**
 * The loads behind the entity pages (artist, album), shared by the pages themselves and by the
 * pointerdown prefetch, through one stale-while-revalidate cache.
 *
 * Keeping them here rather than inside the components is what lets a press on a link start the
 * page's request before the page exists, and the page pick that same request up when it mounts
 * (docs/designs/perceived-performance/technical.md).
 */
import { credentials } from "./store.js";
import { createEntityCache } from "./entityCache.js";
import { registerPrefetcher } from "./entitySeeds.js";
import { listOf, subsonicJson } from "./subsonic.js";

/** The one cache every entity page reads and writes. */
export const entityCache = createEntityCache();

// Another account signing in on the same device must never see the first one's answers (its
// star state above all); signing out and in as the same user may keep them.
let cachedFor = null;
credentials.subscribe((value) => {
  const username = value?.username ?? "";
  if (cachedFor !== null && cachedFor !== username) entityCache.clear();
  cachedFor = username;
});

/** Thrown when the server answered but did not know the id. */
export class EntityNotFound extends Error {
  /** @param {string} kind @param {string} id */
  constructor(kind, id) {
    super(`No ${kind} with id ${id}`);
    this.name = "EntityNotFound";
  }
}

/** @param {string} id */
export const artistKey = (id) => `artist:${id}`;
/** @param {string} id */
export const artistInfoKey = (id) => `artist-info:${id}`;
/**
 * The first page of an artist's tracks depends on the listening mode and the dedupe setting.
 *
 * @param {string} id
 * @param {string} mode - `songs` or `sets`.
 * @param {boolean} dedupe
 */
export const artistTracksKey = (id, mode, dedupe) =>
  `artist-tracks:${id}:${mode}:${dedupe ? "dedupe" : "all"}`;
/** @param {string} id */
export const albumKey = (id) => `album:${id}`;
/** @param {string} id */
export const albumInfoKey = (id) => `album-info:${id}`;
/** A feed's first page, as `loadFeedDetail` returns it. @param {string} slug */
export const feedKey = (slug) => `feed:${slug}`;
/** Every version of one song (`song:<workId>`). @param {string|number} workId */
export const songVersionsKey = (workId) => `song-versions:${workId}`;

/**
 * `getArtist`: the artist with its albums.
 *
 * @param {string} id
 * @returns {Promise<Record<string, any>>}
 */
export async function fetchArtist(id) {
  const data = await subsonicJson("getArtist", { id });
  const artist = data?.["subsonic-response"]?.artist;
  if (!artist) throw new EntityNotFound("artist", id);
  return artist;
}

/**
 * `getArtistInfo2`, flattened to what the artist page shows. Every field is always present,
 * empty when the artist has none.
 *
 * @param {string} id
 * @returns {Promise<{similarArtists: Array<object>, biography: string, mbid: string}>}
 */
export async function fetchArtistInfo(id) {
  const data = await subsonicJson("getArtistInfo2", { id });
  const response = data?.["subsonic-response"] ?? {};
  const info = response.artistInfo || response.artistInfo2 || {};
  const similar = info.similarArtist;
  return {
    similarArtists: similar ? (Array.isArray(similar) ? similar : [similar]) : [],
    biography: info.biography || "",
    mbid: info.musicBrainzId || "",
  };
}

/**
 * `getAlbum`: the album and its songs.
 *
 * @param {string} id
 * @returns {Promise<{album: Record<string, any>, tracks: Array<object>}>}
 */
export async function fetchAlbum(id) {
  const data = await subsonicJson("getAlbum", { id });
  const album = data?.["subsonic-response"]?.album;
  if (!album) throw new EntityNotFound("album", id);
  return { album, tracks: listOf(data, "album.song") };
}

/**
 * `getAlbumInfo2`, or `null` when the server has nothing.
 *
 * @param {string} id
 * @returns {Promise<Record<string, any>|null>}
 */
export async function fetchAlbumInfo(id) {
  const data = await subsonicJson("getAlbumInfo2", { id });
  return data?.["subsonic-response"]?.albumInfo ?? null;
}

/**
 * Starts the artist page's main request; see `pressEntity`.
 *
 * @param {string} id
 */
export function prefetchArtist(id) {
  return entityCache.load(artistKey(id), () => fetchArtist(id));
}

/**
 * Starts the album page's request; see `pressEntity`.
 *
 * @param {string} id
 */
export function prefetchAlbum(id) {
  return entityCache.load(albumKey(id), () => fetchAlbum(id));
}

registerPrefetcher("artist", prefetchArtist);
registerPrefetcher("album", prefetchAlbum);
