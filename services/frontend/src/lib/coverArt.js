import { get, writable } from "svelte/store";
import { restUrl } from "./store.js";
import { offline } from "./subsonic.js";
import { platform as defaultPlatform } from "./platform/index.js";
import { getArtistImageUrl, primaryArtistOf } from "./utils.js";

/**
 * Where an `<img src>` for album art points.
 *
 * Online it is `/rest/getCoverArt`, as it has always been. Offline the shell
 * answers `getCoverArt` with `{status: 'ok', url}` -- a `_capacitor_file_`
 * address the WebView loads straight off disk, so the artwork costs one local
 * request per row rather than a bridge round trip carrying bytes. Art this
 * device never cached comes back as error code 70, and that row keeps the
 * placeholder every other missing cover already uses.
 *
 * The resolution is asynchronous and a `src` is not, so the answers live in a
 * store: a screen renders the placeholder first and swaps the file in when it
 * arrives. Online that store stays empty and nothing here runs at all.
 */

/** What a row with no art shows; the same file the rest of the app falls back to. */
export const FALLBACK = "/images/spotify-fallback.svg";

/**
 * Resolved local artwork, `coverArt id -> url`, with `null` for "asked, and
 * this device does not have it" so the same id is not asked about twice.
 *
 * @type {import('svelte/store').Writable<Record<string, string|null>>}
 */
export const localCoverArt = writable({});

/** Ids currently being resolved, so a re-render does not queue them again. */
const inFlight = new Set();

/**
 * The `src` for one cover.
 *
 * @param {string|number|undefined} id - The track's or album's `coverArt`.
 * @param {number} size - Pixels, for the server; the local file has one size.
 * @param {string} auth - `$authParams`.
 * @param {Record<string, string|null>} [local] - `$localCoverArt`; passing it
 *   explicitly is what makes a component re-render when an answer lands.
 * @param {boolean} [isOffline] - `$offline`.
 * @returns {string}
 */
export function coverArtSrc(id, size, auth, local = {}, isOffline = false) {
  if (!id) return FALLBACK;
  const resolved = local[String(id)];
  if (resolved) return resolved;
  // Offline and not resolved yet, or resolved to nothing: the placeholder. The
  // server URL would only produce a failed request and a flash of broken image.
  if (isOffline) return FALLBACK;
  return restUrl(`/rest/getCoverArt?id=${id}&size=${size}&${auth}`);
}

/**
 * Asks the device for the artwork of the ids a list is about to draw.
 *
 * A no-op online and in a browser, so a caller needs no branch around it.
 *
 * @param {Array<string|number|undefined>} ids
 * @param {object} [platform] - Injected by the tests.
 * @returns {Promise<void>}
 */
export async function resolveCoverArt(ids, platform = defaultPlatform) {
  const storage = platform?.storage;
  if (!storage?.supported || !get(offline)) return;

  const known = get(localCoverArt);
  const wanted = [
    ...new Set(
      (ids ?? [])
        .filter(Boolean)
        .map(String)
        .filter((id) => !(id in known) && !inFlight.has(id)),
    ),
  ];
  if (!wanted.length) return;

  for (const id of wanted) inFlight.add(id);
  await Promise.all(
    wanted.map(async (id) => {
      try {
        const body = await storage.query({ method: "getCoverArt", params: { id } });
        const node = body?.["subsonic-response"];
        // `{status: 'ok', url}` or `{error: {code: 70}}`; anything else is
        // treated as "no art", which is what the placeholder already says.
        const url = node?.status === "ok" && node?.url ? String(node.url) : null;
        localCoverArt.update((current) => ({ ...current, [id]: url }));
      } catch (error) {
        console.warn("Could not resolve local cover art", id, error);
        localCoverArt.update((current) => ({ ...current, [id]: null }));
      } finally {
        inFlight.delete(id);
      }
    }),
  );
}

/**
 * Artist image URLs that answered with an error this session.
 *
 * MuMa says "no portrait for this artist" with a 404, and a browser does not
 * cache a 404 -- so without this every row of the same artist asks again on
 * every render, and each miss makes the server queue another lookup at
 * Spotify. `Artwork.svelte` records a failed URL here and
 * [artistImageFallback] answers `null` for it from then on, so the row starts
 * at the panel instead of flashing through a request it already knows the
 * outcome of.
 *
 * @type {Set<string>}
 */
export const missingArtistImages = new Set();

/**
 * The picture a track without a cover falls back to: its first artist's
 * portrait, or `null` when there is no artist to ask for or MuMa already said
 * it has none.
 *
 * `getArtistImageUrl` answers "nothing to build a URL from" with the
 * unknown-artist placeholder rather than `null`; that is recognised here so
 * `Artwork` does not treat a placeholder path as a real portrait and skip its
 * own panel.
 *
 * @param {object|null|undefined} track - A Subsonic track.
 * @param {string} auth - `$authParams`.
 * @returns {string|null}
 */
export function artistImageFallback(track, auth) {
  const artist = primaryArtistOf(track);
  if (!artist) return null;
  const url = getArtistImageUrl(artist, auth);
  if (url === "/images/unknown-artist.svg" || missingArtistImages.has(url)) return null;
  return url;
}

/** Forgets every resolved cover, which is what a removed download invalidates. */
export function forgetCoverArt() {
  inFlight.clear();
  localCoverArt.set({});
}
