/**
 * Optimistic navigation: what a link already knows about the thing it opens.
 *
 * A track row knows its artist's name; an album tile knows the title, the cover and the
 * artist. The page behind the link used to throw that away and show "Loading..." until the
 * server had said the same things again. A link now leaves a *seed* here before it navigates,
 * and the page renders its header from the seed at once, with skeletons for what still needs
 * data (docs/designs/perceived-performance/).
 *
 * A seed is only ever a stand-in: the page replaces it with the server's answer as soon as
 * that arrives, so a wrong guess corrects itself instead of sticking.
 */

/** How many seeds are kept. Oldest go first; a seed is only useful for the next few taps. */
export const MAX_SEEDS = 200;

/** Fields a seed may carry. Anything else on the object it is built from is ignored. */
const SEED_FIELDS = [
  "name",
  "coverArt",
  "artistImageUrl",
  "artist",
  "artistId",
  "year",
  // A feed card's second line ("Zachter" / "≤ 42 hardheid"), for the feed page's header.
  "subtitle",
];

/** @type {Map<string, Record<string, any>>} */
const seeds = new Map();

/** @type {Map<string, (id: string) => unknown>} kind -> prefetcher, see `registerPrefetcher`. */
const prefetchers = new Map();

/** @type {Map<string, () => unknown>} kind -> page chunk loader, see `registerPagePreloader`. */
const pagePreloaders = new Map();

/**
 * @param {string} kind
 * @param {string|number} id
 */
function keyOf(kind, id) {
  return `${kind}:${id}`;
}

/**
 * Remembers what is known about `kind:id`. Empty fields never overwrite known ones, so a later,
 * poorer link (a bare id) cannot erase what a richer one left.
 *
 * @param {string} kind - `artist`, `album`...
 * @param {string|number|null|undefined} id
 * @param {Record<string, any>|null|undefined} seed
 */
export function seedEntity(kind, id, seed) {
  if (id === null || id === undefined || id === "" || !seed) return;
  const key = keyOf(kind, id);
  const merged = { ...seeds.get(key) };
  for (const field of SEED_FIELDS) {
    const value = seed[field];
    if (value !== undefined && value !== null && value !== "") merged[field] = value;
  }
  seeds.delete(key);
  seeds.set(key, merged);
  while (seeds.size > MAX_SEEDS) seeds.delete(seeds.keys().next().value);
}

/**
 * What a link left for `kind:id`, or `null`.
 *
 * @param {string} kind
 * @param {string|number} id
 * @returns {Record<string, any>|null}
 */
export function peekSeed(kind, id) {
  const seed = seeds.get(keyOf(kind, id));
  return seed && Object.keys(seed).length > 0 ? { ...seed } : null;
}

/** Forgets every seed; for the tests and a sign-out. */
export function clearSeeds() {
  seeds.clear();
}

/**
 * The artist seed a track row carries: its first artist's id and the name shown for it.
 *
 * @param {Record<string, any>|null|undefined} track
 * @returns {{id: string, seed: Record<string, any>}|null}
 */
export function artistSeedFromTrack(track) {
  if (!track) return null;
  const first = Array.isArray(track.artists) && track.artists.length > 0 ? track.artists[0] : null;
  if (first?.id) return { id: String(first.id), seed: { name: first.name } };
  if (!track.artistId) return null;
  // A legacy comma-joined credit ("A, B"): the id belongs to the first name only, which is
  // exactly the rule `ArtistList` uses when it draws the names.
  const name = typeof track.artist === "string" ? track.artist.split(", ")[0] : undefined;
  return { id: String(track.artistId), seed: { name } };
}

/**
 * The album seed a track row carries.
 *
 * @param {Record<string, any>|null|undefined} track
 * @returns {{id: string, seed: Record<string, any>}|null}
 */
export function albumSeedFromTrack(track) {
  if (!track?.albumId) return null;
  return {
    id: String(track.albumId),
    seed: {
      name: track.album,
      coverArt: track.coverArt,
      artist: track.albumArtist || track.artist,
      year: track.year,
    },
  };
}

/**
 * Seeds `entity` and navigates to its page -- the drop-in for `onnavigate(\`artist:${id}\`)`.
 * Works with any navigate function, the `onnavigate` prop and Dashboard's `activeView = v` alike.
 *
 * @param {((view: string) => void)|null|undefined} navigate
 * @param {string} kind
 * @param {Record<string, any>|null|undefined} entity - Must carry `id`.
 */
export function openEntity(navigate, kind, entity) {
  if (!entity?.id) return;
  seedEntity(kind, entity.id, entity);
  navigate?.(keyOf(kind, entity.id));
}

/**
 * Registers how to prefetch a kind's main request. `entityLoaders.js` does this for artists and
 * albums; kept as a registry so this module imports nothing and every list can use it cheaply.
 *
 * @param {string} kind
 * @param {(id: string) => unknown} prefetcher
 */
export function registerPrefetcher(kind, prefetcher) {
  prefetchers.set(kind, prefetcher);
}

/**
 * Registers how to start fetching a kind's page chunk. `lazyViews.js` does this for the artist,
 * album and feed pages (issue #118), so a press fetches the page's code together with its data.
 *
 * @param {string} kind
 * @param {() => unknown} preloader
 */
export function registerPagePreloader(kind, preloader) {
  pagePreloaders.set(kind, preloader);
}

/**
 * Starts a kind's registered page chunk, swallowing a failure: the page itself retries.
 *
 * @param {string} kind
 */
function preloadPage(kind) {
  const preload = pagePreloaders.get(kind);
  if (!preload) return;
  try {
    const result = preload();
    if (result && typeof result.catch === "function") result.catch(() => {});
  } catch {
    // A preload never breaks the tap it rides on.
  }
}

/**
 * A finger (or a mouse button) went down on a link: seed it, start the page's chunk and its
 * main request, which the page then shares instead of making its own. One request per press, never on hover
 * or scroll -- LMS serves every client from one small thread pool.
 *
 * @param {string} kind
 * @param {Record<string, any>|null|undefined} entity - Must carry `id`.
 */
export function pressEntity(kind, entity) {
  if (!entity?.id) return;
  seedEntity(kind, entity.id, entity);
  preloadPage(kind);
  const prefetch = prefetchers.get(kind);
  if (!prefetch) return;
  try {
    const result = prefetch(String(entity.id));
    // A prefetch that fails is the page's problem to report, not the press's.
    if (result && typeof result.catch === "function") result.catch(() => {});
  } catch {
    // Same: never let a prefetch break the tap it rides on.
  }
}

/**
 * Seeds both the artist and the album a track row points at, for a "go to album/artist" link
 * that has the track rather than the entity in hand.
 *
 * @param {Record<string, any>|null|undefined} track
 */
export function seedFromTrack(track) {
  const artist = artistSeedFromTrack(track);
  if (artist) seedEntity("artist", artist.id, artist.seed);
  const album = albumSeedFromTrack(track);
  if (album) seedEntity("album", album.id, album.seed);
}

/**
 * The seed for a song's versions page (`song:<workId>`), from the track row that was tapped:
 * the title, the artist line and the cover the row was already showing.
 *
 * @param {Record<string, any>|null|undefined} track
 * @returns {{id: string, seed: Record<string, any>}|null}
 */
export function songSeedFromTrack(track) {
  if (!track?.workId) return null;
  return {
    id: String(track.workId),
    seed: {
      name: track.title,
      artist: track.artist,
      artistId: track.artistId,
      coverArt: track.coverArt,
    },
  };
}

/**
 * Seeds and opens the versions page of the song `track` belongs to -- the drop-in for
 * `onnavigate(\`song:${track.workId}\`)`.
 *
 * @param {((view: string) => void)|null|undefined} navigate
 * @param {Record<string, any>|null|undefined} track - Must carry `workId`.
 */
export function openSong(navigate, track) {
  const song = songSeedFromTrack(track);
  if (!song) return;
  seedEntity("song", song.id, song.seed);
  navigate?.(keyOf("song", song.id));
}
