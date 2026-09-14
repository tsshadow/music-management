import { get, writable } from "svelte/store";
import { authParams, restUrl } from "./store.js";
import { platform as defaultPlatform } from "./platform/index.js";

/**
 * One way in to `/rest/*`, so that a list never learns a second data source.
 *
 * This belongs next to `restUrl` in `store.js` and lives here instead for one
 * reason: `store.js` is imported by `platform/browser/system.js`, so a
 * `platform` import there would close a cycle. Everything else about it is the
 * `restUrl` story continued -- callers name a method and its parameters and get
 * back the body LMS answers with, whoever actually answered.
 *
 * ### The switch
 *
 * Three rules, in this order:
 *
 * 1. `platform.storage.supported === false` -- a plain browser tab -- always
 *    fetches. Nothing below runs, which is what keeps criterion 13 ("no other
 *    screen differs") true by construction rather than by testing.
 * 2. Inside a shell that reports itself offline, `platform.storage.isOffline()`
 *    is asked again first -- cheap, a bridge call rather than a network round
 *    trip -- because the flag can be minutes old and set from a single earlier
 *    blip. Confirmed, the request goes straight to `platform.storage.query`: no
 *    fetch is attempted, which on a phone in a tunnel is twenty seconds of
 *    spinner per list. Not confirmed, the flag was stale and clears before
 *    falling through to rule 3, so a connection that came back is used the
 *    moment anything asks again rather than waiting for a connectivity event.
 * 3. Inside a shell that believes it is online, the server is tried first and a
 *    *network* failure asks `isOffline()` once more before falling back to the
 *    local library. Only a confirmed "no route" flips the flag and uses the
 *    device; anything else is a transient failure and travels to the caller
 *    exactly as it would in a browser tab, because a single dropped request is
 *    not the same claim as "this device has no way to reach a server", and
 *    must not be allowed to make every later screen believe that until an
 *    unrelated connectivity event fires.
 *
 * An HTTP status is deliberately not a reason to fall back. A 401 or a 500 is
 * the server answering, and answering the listener's own library instead would
 * turn "your password expired" into "your library shrank".
 *
 * The body is returned exactly as it arrives, `{"subsonic-response": {...}}`
 * either way, so no caller can tell which side answered.
 */

/**
 * Whether the shell last reported having no route to the server.
 *
 * A store rather than a call, because screens branch on it while rendering:
 * the Downloads tab, the empty states, and the "not available without a
 * connection" notice all read it. It only ever becomes true inside a shell --
 * `platform.storage.supported` gates every writer.
 *
 * @type {import('svelte/store').Writable<boolean>}
 */
export const offline = writable(false);

/** The methods the offline library can answer; see `OfflineSubsonic.kt`. */
export const OFFLINE_METHODS = Object.freeze([
  "ping",
  "getGenres",
  "getYears",
  "getRecordLabels",
  "getSpotifyTracks",
  "getAlbumList2",
  "getAlbum",
  "getArtist",
  "getArtistList",
  "getSong",
  "search3",
  "getStarred2",
  "getCoverArt",
  "getPlaylists",
  "getPlaylist",
]);

/** The empty success body, which is what "the device cannot answer that" looks like. */
const EMPTY_BODY = Object.freeze({ "subsonic-response": { status: "ok", version: "1.16.1" } });

/**
 * Starts following the shell's connectivity, and asks once for the current
 * answer so nothing has to guess before the first change arrives.
 *
 * @param {object} [platform] - Injected by the tests.
 * @returns {function(): void} Unsubscribes.
 */
export function watchConnectivity(platform = defaultPlatform) {
  const storage = platform?.storage;
  if (!storage?.supported) return () => {};

  Promise.resolve(storage.isOffline())
    .then((value) => offline.set(value === true))
    .catch((error) => console.warn("Could not read the connectivity state", error));

  return storage.onConnectivity(({ online }) => offline.set(online !== true));
}

/**
 * Turns a parameter object into a query string.
 *
 * `undefined`, `null` and `''` are dropped rather than sent as empty: LMS reads
 * `genre=` as a genre whose name is the empty string and answers nothing, which
 * is how a filter nobody set empties a list.
 *
 * @param {Record<string, unknown>} params
 * @returns {string}
 */
export function queryString(params = {}) {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join("&");
}

/**
 * Whether a thrown error means "the request never reached a server".
 *
 * `fetch` rejects with a `TypeError` for DNS, connection and CORS failures, so
 * that is the check -- not "anything that isn't an abort". A response that
 * did arrive but was not JSON (a proxy's HTML error page, a captive portal)
 * throws a `SyntaxError` out of `response.json()`, and that is the server
 * answering, however badly; treating it as "no route to a server" would fall
 * back to the device on exactly the kind of error rule 3's own comment above
 * says must not do that. An abort is the caller's own doing and travels on
 * regardless of its constructor.
 *
 * @param {unknown} error
 * @returns {boolean}
 */
function isNetworkFailure(error) {
  return error instanceof TypeError && error.name !== "AbortError";
}

/**
 * Asks the shell's own connectivity signal fresh, rather than trusting
 * whatever the `offline` store currently holds.
 *
 * Cheap -- a bridge call answered from the OS, not a network round trip --
 * which is why both the fast path (skip the fetch outright when the flag is
 * already set) and the failure path (decide whether a failed request means
 * "offline" at all) confirm through here instead of a flag that a single
 * earlier blip could have set minutes ago.
 *
 * @param {object} storage
 * @returns {Promise<boolean>}
 */
async function confirmedOffline(storage) {
  try {
    return (await storage.isOffline()) === true;
  } catch (error) {
    console.warn("Could not read the connectivity state", error);
    return false;
  }
}

/**
 * Makes one `/rest` call and hands back the parsed body.
 *
 * @param {string} method - A `/rest` method name, e.g. `getSpotifyTracks`.
 * @param {Record<string, unknown>} [params] - Everything but the credentials.
 * @param {object} [options]
 * @param {AbortSignal} [options.signal] - Travels to `fetch` only; a local
 *   query is a bridge call that finishes in milliseconds.
 * @param {object} [options.platform] - Injected by the tests.
 * @param {typeof fetch} [options.fetchImpl] - Injected by the tests.
 * @returns {Promise<object>} The `{"subsonic-response": ...}` body.
 * @throws {Error} Only when there is no local library to fall back to, so that
 *   a browser tab keeps behaving exactly as it did.
 */
export async function subsonicJson(method, params = {}, options = {}) {
  const { signal, platform = defaultPlatform, fetchImpl } = options;
  const storage = platform?.storage;
  const local = storage?.supported === true;

  if (local && get(offline)) {
    if (await confirmedOffline(storage)) return await localQuery(storage, method, params);
    // The device now says it has a route again. A flag flipped by one earlier
    // blip must not keep outliving the connection problem it recorded, so it
    // clears here rather than waiting for an unrelated connectivity event.
    offline.set(false);
  }

  try {
    const call = fetchImpl ?? fetch;
    const auth = get(authParams);
    const query = [auth, queryString(params)].filter(Boolean).join("&");
    const response = await call(restUrl(`/rest/${method}?${query}`), signal ? { signal } : {});
    return await response.json();
  } catch (error) {
    if (!local || !isNetworkFailure(error)) throw error;
    if (!(await confirmedOffline(storage))) throw error;
    // The method is an argument rather than interpolated: a name that reached a
    // log line as a format string could forge the rest of the message, and
    // semgrep's `unsafe-formatstring` is right to say so even here.
    console.info("The server did not answer /rest/%s; using what is on the device", method, error);
    offline.set(true);
    return await localQuery(storage, method, params);
  }
}

/**
 * Asks the device, and treats its failure as "nothing is downloaded".
 *
 * @param {object} storage
 * @param {string} method
 * @param {Record<string, unknown>} params
 * @returns {Promise<object>}
 */
async function localQuery(storage, method, params) {
  try {
    const body = await storage.query({ method, params: plain(params) });
    return body && typeof body === "object" ? body : EMPTY_BODY;
  } catch (error) {
    console.warn("The device could not answer %s", method, error);
    return EMPTY_BODY;
  }
}

/**
 * Drops the parameters that were left out, so the bridge carries a JSON object
 * the Kotlin side can read with `optString` without seeing `"undefined"`.
 *
 * @param {Record<string, unknown>} params
 * @returns {Record<string, string>}
 */
function plain(params) {
  return Object.fromEntries(
    Object.entries(params ?? {})
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
}

/**
 * Reads one node out of a body and always hands back an array.
 *
 * Subsonic collapses a one-element list into a bare object, which every caller
 * in this app has its own `Array.isArray(...) ? ... : [...]` for. One copy.
 *
 * @param {object} body - The `{"subsonic-response": ...}` body.
 * @param {string} path - Dotted, e.g. `tracks.track`.
 * @returns {Array<object>}
 */
export function listOf(body, path) {
  let node = body?.["subsonic-response"];
  for (const step of path.split(".")) node = node?.[step];
  if (node === undefined || node === null) return [];
  return Array.isArray(node) ? node : [node];
}

/**
 * The views that still have something to show without a connection.
 *
 * Everything else -- the personal feeds, memories, history, listening stats,
 * the tag collections -- is a server answer or nothing, and says so rather
 * than spinning.
 *
 * @param {string} view - An `activeView` identifier.
 * @returns {boolean}
 */
export function viewHasOfflineSource(view) {
  if (typeof view !== "string") return false;
  if (OFFLINE_VIEWS.has(view)) return true;
  return OFFLINE_VIEW_PREFIXES.some((prefix) => view.startsWith(prefix));
}

const OFFLINE_VIEWS = new Set([
  "home",
  "songs",
  "sets",
  "albums",
  "artists",
  "genres",
  "labels",
  "starred",
  "downloads",
  "settings",
  "playlists",
  "playlist-detail",
]);

// `label:` and `year:` are here and `podcast:`, `festival:` and `lineup:` are
// not, because those are the filters `getSpotifyTracks` takes on the offline
// side. A view whose filter the device cannot apply would otherwise list the
// whole downloaded library under someone else's name.
const OFFLINE_VIEW_PREFIXES = [
  "genre:",
  "label:",
  "year:",
  "artist:",
  "album:",
  "song:",
  "search:",
];
