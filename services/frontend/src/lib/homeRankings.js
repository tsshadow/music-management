/**
 * Home's personalised rankings: the account's most-played artists and labels over the
 * last 30 days, and the lookup from a ranking's artist name to the LMS view `onnavigate`
 * needs to open it.
 *
 * Split out of `PhoneHome.svelte` because the two things that can quietly go wrong here --
 * a `/api/listening` call failing, and a name not matching any artist in the library --
 * are exactly the parts worth testing without rendering a component. `listeningStats.js`
 * already owns the endpoint shape and the "one endpoint's failure must not blank the
 * others" contract; this reuses both rather than inventing a second copy.
 */
import { listeningUrl, periodRange } from "./listeningStats.js";
import { getHeaders } from "./mumaApi.js";
import { listOf, subsonicJson } from "./subsonic.js";

/** How many rows a Home strip shows -- enough to fill a horizontal scroll without asking
 * MuMa for a whole top-20 list nobody will scroll to. */
const RANKING_LIMIT = 8;

/**
 * The account's most-played artists in the last 30 days, newest listening window only:
 * a lifetime ranking would barely move month to month and would not read as "yours
 * this month". Fails soft to `[]` -- a network error, a non-OK response, or a body that
 * does not parse -- so a broken ranking never blanks the rest of Home, same as every
 * panel in `loadListening`.
 *
 * @param {typeof fetch} [fetcher] - Injectable for tests.
 * @returns {Promise<Array<{name: string, listens: number}>>}
 */
export async function loadTopArtists(fetcher = fetch) {
  const rows = await rankingRows("top-artists", "artists", fetcher);
  return rows.map((row) => ({ name: row.artist, listens: row.listens }));
}

/**
 * The account's most-played labels in the last 30 days. Same contract as `loadTopArtists`.
 *
 * @param {typeof fetch} [fetcher] - Injectable for tests.
 * @returns {Promise<Array<{name: string, listens: number}>>}
 */
export async function loadTopLabels(fetcher = fetch) {
  const rows = await rankingRows("top-labels", "labels", fetcher);
  return rows.map((row) => ({ name: row.label, listens: row.listens }));
}

/**
 * GETs one `/api/listening` ranking endpoint and hands back its rows, or none at all
 * when anything about the request goes wrong.
 *
 * @param {string} path - The endpoint below `/api/listening`, e.g. `top-artists`.
 * @param {string} listKey - The array field the endpoint's body carries the rows under.
 * @param {typeof fetch} fetcher
 * @returns {Promise<Array<object>>}
 */
async function rankingRows(path, listKey, fetcher) {
  try {
    const response = await fetcher(
      listeningUrl(path, { ...periodRange("30d"), limit: RANKING_LIMIT }),
      {
        headers: getHeaders(),
      },
    );
    if (!response.ok) return [];
    const body = await response.json();
    return body?.[listKey] ?? [];
  } catch {
    return [];
  }
}

/**
 * `artist:<lmsId>` views already resolved this session, keyed by the artist name that
 * was looked up. A page reload is the only time an artist's LMS id could change, so
 * nothing here needs to expire; it exists only so two rankings sharing an artist, or a
 * re-render of the same strip, do not repeat the lookup. Holding the *promise* rather
 * than its result also means two calls for the same name while the first is still in
 * flight share that one request instead of firing a second.
 *
 * @type {Map<string, Promise<string|null>>}
 */
const resolvedArtistViews = new Map();

/**
 * The LMS `artist:<id>` view for a ranking's artist name, or `null` when nothing in the
 * library matches it -- the caller falls back to `search:<name>` in that case, since a
 * name search always finds *something* even when the exact artist entity does not.
 *
 * MuMa's own `artist_id` (carried by `/api/listening/top-artists`) is never used for
 * this: it identifies a row in MuMa's own artist table, not an LMS entity, and handing
 * it to a `artist:<id>` view would open the wrong artist or nothing at all. This goes
 * through `search3` instead, the same lookup every other artist tap in this app uses.
 *
 * @param {string} name
 * @returns {Promise<string|null>}
 */
export function resolveArtistView(name) {
  if (resolvedArtistViews.has(name)) return resolvedArtistViews.get(name);
  const promise = lookupArtistView(name);
  resolvedArtistViews.set(name, promise);
  return promise;
}

/** The uncached, un-memoised lookup `resolveArtistView` wraps. */
async function lookupArtistView(name) {
  try {
    const data = await subsonicJson("search3", {
      query: name,
      artistCount: 3,
      albumCount: 0,
      songCount: 0,
    });
    const artists = listOf(data, "searchResult3.artist");
    if (artists.length === 0) return null;
    const exact = artists.find((artist) => artist.name?.toLowerCase() === name.toLowerCase());
    const match = exact ?? artists[0];
    return match?.id ? `artist:${match.id}` : null;
  } catch {
    return null;
  }
}
