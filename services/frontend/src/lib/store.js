import { writable, derived, get, readable } from "svelte/store";
import { locale, setLocaleFromAccount, resetLocaleToBrowser, currentLocale } from "./i18n/index.js";
import {
  EQ_FREQUENCIES,
  EQ_GAIN_MIN,
  EQ_GAIN_MAX,
  EQ_PRESETS,
  CUSTOM_PRESET,
} from "./equalizerPresets.js";
import { gatedFetch } from "./mumaGate.js";
import { md5 } from "./md5.js";

/**
 * Every store handed to {@link persist}, with the value it was declared with, so a logout can put
 * each one back without a hand-kept list that a new store would be missing from. `device: true`
 * marks the few that describe this browser rather than the person signed in to it.
 *
 * @type {Array<{key: string, store: import('svelte/store').Writable, initial: string, device: boolean}>}
 */
const persistedStores = [];

// Helper to persist store to localStorage
/**
 * Persists a Svelte store to localStorage.
 * Automatically loads the value on initialization and subscribes to changes.
 *
 * @param {string} key - The localStorage key to use.
 * @param {import('svelte/store').Writable} store - The store to persist.
 * @param {Object} [options] - Optional configuration.
 * @param {function(any): any} [options.onLoad] - Transformation function applied to the loaded value.
 * @param {boolean} [options.device] - Kept across a logout; see {@link resetSessionState}.
 * @param {number} [options.throttleMs] - Write at most once per this many milliseconds, for a store
 *   that changes several times a second (`playerState`'s progress). The first change after a quiet
 *   spell is written at once, later ones are coalesced into one trailing write of the latest value,
 *   and {@link flushPersistedStores} -- run on pause, on `visibilitychange` to hidden and on
 *   `pagehide` -- writes whatever is still pending, so the last position is never lost.
 */
function persist(key, store, options = {}) {
  const entry = {
    key,
    store,
    initial: JSON.stringify(get(store)),
    device: options.device === true,
    flush: () => {},
    cancel: () => {},
  };
  persistedStores.push(entry);
  const json = localStorage.getItem(key);
  if (json) {
    try {
      const parsed = JSON.parse(json);
      if (options.onLoad) {
        store.set(options.onLoad(parsed));
      } else {
        store.set(parsed);
      }
    } catch (e) {
      console.error(`Failed to parse stored value for ${key}`, e);
    }
  }

  const write = (value) => localStorage.setItem(key, JSON.stringify(value));
  if (!options.throttleMs) {
    store.subscribe(write);
    return;
  }
  const throttled = throttledWriter(write, options.throttleMs);
  entry.flush = throttled.flush;
  entry.cancel = throttled.cancel;
  store.subscribe(throttled.push);
}

/**
 * Wraps a writer so it runs at most once per `intervalMs`: leading write, then one trailing write
 * of the latest value. `flush` writes a pending value now; `cancel` drops it.
 *
 * @template T
 * @param {function(T): void} write
 * @param {number} intervalMs
 * @param {object} [clock] - Injected by the tests.
 * @param {function(): number} [clock.now]
 * @returns {{push: function(T): void, flush: function(): void, cancel: function(): void}}
 */
export function throttledWriter(write, intervalMs, { now = () => Date.now() } = {}) {
  let lastWriteAt = -Infinity;
  let timer = null;
  let pending = false;
  let latest;

  function flush() {
    clearTimeout(timer);
    timer = null;
    if (!pending) return;
    pending = false;
    lastWriteAt = now();
    write(latest);
  }

  function cancel() {
    clearTimeout(timer);
    timer = null;
    pending = false;
  }

  function push(value) {
    latest = value;
    pending = true;
    const wait = lastWriteAt + intervalMs - now();
    if (wait <= 0) flush();
    else if (!timer) timer = setTimeout(flush, wait);
  }

  return { push, flush, cancel };
}

/**
 * Writes every throttled store's pending value to localStorage now. Called when the page may be
 * about to go away (hidden, `pagehide`) and when playback pauses, so the throttle never costs the
 * last known position.
 */
export function flushPersistedStores() {
  for (const entry of persistedStores) entry.flush();
}

if (typeof window !== "undefined") {
  window.addEventListener("pagehide", flushPersistedStores);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushPersistedStores();
  });
}

/**
 * The Subsonic base a fresh browser session starts with: an explicit
 * per-deployment override, empty during `vite dev` (the dev server proxies
 * `/rest/*` itself, so a relative URL is exactly right), or the page's own
 * origin otherwise. `restUrl()` below falls back to the same origin at
 * request time, so this and that fallback always agree.
 *
 * @returns {string}
 */
export function defaultSubsonicUrl() {
  return import.meta.env.VITE_SUBSONIC_URL || (import.meta.env.DEV ? "" : window.location.origin);
}

export const credentials = writable({
  url: defaultSubsonicUrl(),
  username: "",
  password: "",
});
persist("lms_credentials", credentials);

/**
 * The signed-in user's own Subsonic API token, and the LMS login name it was
 * issued for (`GET /api/auth/subsonic-token`, see `refreshSubsonicToken`).
 * While it matches `credentials.username`, every Subsonic URL is signed with
 * `t=md5(token + salt)&s=salt` instead of carrying the password as `p=` --
 * which put the password in every stream, cover and API URL, and so in every
 * access log and browser history entry on the way (bug report 103).
 */
export const subsonicToken = writable({ username: "", token: "" });
persist("lms_subsonic_token", subsonicToken);

/**
 * A random salt as hex. `authParams` draws one per page session and token (see
 * `sessionSaltFor`), not per request: the URLs a page builds stay stable, so
 * the browser's image cache keeps working, while no URL carries the token or
 * the password.
 *
 * @returns {string}
 */
export function freshSalt() {
  const bytes = new Uint8Array(12);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** The salt drawn for the current token; see `sessionSaltFor`. */
let sessionSalt = { token: "", salt: "" };

/**
 * The salt `authParams` signs with while `token` is the token: drawn once and
 * kept until the token changes or the page reloads. A derived store read with
 * `get()` and no subscriber recomputes on every read, so the salt cannot live
 * in the derivation itself.
 *
 * @param {string} token
 * @returns {string}
 */
function sessionSaltFor(token) {
  if (sessionSalt.token !== token || !sessionSalt.salt) sessionSalt = { token, salt: freshSalt() };
  return sessionSalt.salt;
}

/**
 * The Subsonic query string that signs a request as `username` with a token:
 * `t = md5(token + salt)`, exactly what LMS checks.
 *
 * @param {string} username
 * @param {string} token
 * @param {string} [salt]
 * @returns {string}
 */
export function subsonicTokenQuery(username, token, salt = freshSalt()) {
  return `u=${encodeURIComponent(username)}&t=${md5(token + salt)}&s=${salt}&v=1.12.0&c=spotify&f=json`;
}

export const mumaApiUrl = writable(
  import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "" : "/muma"),
);
// Which MuMa this browser talks to is the device's configuration, not the account's: the next
// person to sign in here reaches the same server.
persist("muma_api_url", mumaApiUrl, { device: true });

/**
 * Builds an absolute Subsonic (`/rest/*`) URL from `credentials.url`, so a
 * request reaches the configured server even when the page it runs on does
 * not share that origin -- inside the Capacitor shell the page origin is
 * `https://localhost`, so a bare `fetch('/rest/...')` would resolve against
 * the WebView instead of the music server.
 *
 * In the browser today `credentials.url` already holds the page's own
 * origin (see `defaultSubsonicUrl` above), so this produces exactly the
 * string a relative fetch would have hit: no behaviour change there.
 *
 * @param {string} pathAndQuery - Starting with `/`, e.g. `/rest/ping?u=...`.
 * @returns {string}
 */
export function restUrl(pathAndQuery) {
  const base = get(credentials).url || window.location.origin;
  return `${base.replace(/\/+$/, "")}${pathAndQuery}`;
}

export const mumaApiKey = writable("");
persist("muma_api_key", mumaApiKey);

export const mumaRefreshToken = writable("");
persist("muma_refresh_token", mumaRefreshToken);

export const mumaSessionActive = writable(false);
persist("muma_session_active", mumaSessionActive);

/**
 * Set by a deliberate logout, cleared by the next successful sign-in. While it is set the Android
 * shell's boot does not sign itself back in from whatever the phone still holds
 * (`restoreSession` in nativeSession.js): a native sign-out that failed or never answered used to
 * leave the password in Kotlin, and the reload after the logout put the user straight back in, so
 * "Uitloggen" visibly did nothing (bug report 106). A device store on purpose: it has to survive
 * the very `resetSessionState` the logout runs.
 */
export const signedOut = writable(false);
persist("muma_signed_out", signedOut, { device: true });

export const userPermissions = writable([]);
export const mumaUser = writable(null);

/**
 * Ends a session the server has stopped accepting -- Subsonic's error 40, a password changed or
 * expired since sign-in. Clears the credentials and the MuMa session, which is what puts
 * App.svelte's login page back up: without this an expired password did not look like an error at
 * all, only like a library that had gone empty. Unlike a logout it keeps the queue and the
 * settings -- whoever signs in next is almost always the same person -- and keeps the server
 * address, which belongs to this device rather than to the account.
 */
export function endRejectedSession() {
  credentials.update((current) => ({ ...current, username: "", password: "" }));
  subsonicToken.set({ username: "", token: "" });
  mumaApiKey.set("");
  mumaRefreshToken.set("");
  mumaSessionActive.set(false);
  userPermissions.set([]);
  mumaUser.set(null);
}

/**
 * Checks if the current user has a specific permission.
 * @param {string} permissionName
 * @returns {boolean}
 */
export function hasPermission(permissionName) {
  const permissions = get(userPermissions);
  const user = get(mumaUser);
  return permissions.includes(permissionName) || user?.is_admin || user?.role_name === "admin";
}

export const currentTrack = writable(null);
persist("lms_current_track", currentTrack);

export const playlist = writable([]);
persist("lms_playlist", playlist);

/**
 * Where the current queue came from -- `{view, name} | null`, set by
 * `queue.js`'s `startQueue()`, never written to directly. Not persisted: a
 * restored queue (jam sync, session rehydration on launch) is not a new
 * start, and `startQueue` clears this rather than guessing a source for it,
 * so a reload always falls back to the track's own album until the listener
 * starts something new. See `docs/designs/phone-ui-polish/technical.md`,
 * section E.
 */
export const queueSource = writable(null);

/**
 * The feed the current queue continues from -- `{slug, nextOffset} | null`, set
 * by `queue.js`'s `startQueue()` for a queue started from a feed and advanced by
 * `feedQueue.js` as it tops the queue up. Any other start clears it, so an album
 * never grows with feed tracks. Not persisted, for the same reason as
 * `queueSource`. See `docs/designs/feed-length/technical.md`.
 */
export const feedContinuation = writable(null);

export const playerState = writable({
  playing: false,
  volume: 50,
  progress: 0,
  duration: 0,
  shuffle: false,
  repeat: "none", // 'none', 'one', 'all'
});
/**
 * How often `playerState` may reach localStorage. Progress changes about four times a second while
 * playing; writing each of those serialised the whole object synchronously on the main thread.
 */
export const PLAYER_STATE_PERSIST_MS = 5000;
persist("lms_player_state", playerState, {
  onLoad: (value) => ({ ...value, playing: false }), // Always start paused
  throttleMs: PLAYER_STATE_PERSIST_MS,
});

/** What a browser that has never touched the equalizer gets. */
export const EQUALIZER_DEFAULT = Object.freeze({
  enabled: false,
  preamp: 0,
  gains: EQ_FREQUENCIES.map(() => 0),
  preset: "flat",
});

function isValidGain(value) {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= EQ_GAIN_MIN &&
    value <= EQ_GAIN_MAX
  );
}

/**
 * Turns whatever is in localStorage into settings the audio graph can trust.
 *
 * A half-valid curve is worse than none: applying it would leave the user with
 * a sound they cannot explain and did not choose. Anything that does not check
 * out completely goes back to flat.
 *
 * @param {unknown} value
 * @returns {{ enabled: boolean, preamp: number, gains: number[], preset: string }}
 */
export function sanitizeEqualizerSettings(value) {
  const fallback = { ...EQUALIZER_DEFAULT, gains: EQUALIZER_DEFAULT.gains.slice() };
  if (!value || typeof value !== "object" || Array.isArray(value)) return fallback;

  const { preamp, gains, preset } = value;
  if (!Array.isArray(gains) || gains.length !== EQ_FREQUENCIES.length) return fallback;
  if (!gains.every(isValidGain)) return fallback;
  if (!isValidGain(preamp)) return fallback;
  if (preset !== CUSTOM_PRESET && !(preset in EQ_PRESETS)) return fallback;

  return {
    enabled: Boolean(value.enabled),
    preamp,
    gains: gains.slice(),
    preset,
  };
}

export const equalizerSettings = writable({
  ...EQUALIZER_DEFAULT,
  gains: EQUALIZER_DEFAULT.gains.slice(),
});
persist("lms_equalizer", equalizerSettings, { onLoad: sanitizeEqualizerSettings });

export const audio = writable(null);
export const currentPlaylist = writable(null);
export const isPlaying = writable(false);
export const activeView = writable("home");
persist("lms_active_view", activeView);

export const viewMode = writable("songs"); // 'songs' or 'sets'
persist("lms_view_mode", viewMode);

export const activeSettingsTab = writable("general");
persist("lms_active_settings_tab", activeSettingsTab);

export const activeManagementTab = writable("overview");
persist("lms_active_management_tab", activeManagementTab);

// The settings and management sidebars are the only way to reach their tabs,
// and the sidebar column is desktop-only. On a narrow screen they are opened
// as a drawer instead; deliberately not persisted -- an overlay that survives
// a reload would cover the screen on arrival.
export const sidebarDrawerOpen = writable(false);

// Whether SearchBar's results panel is currently open, mirrored out of its own
// component state. The phone shell's Android back handler needs this to close
// a search result before it falls through to leaving the Search tab -- and it
// lives in `App.svelte`, not inside SearchBar, so it cannot just read a local
// `$state`. Deliberately not persisted: a reload starts with nothing open.
export const searchResultsOpen = writable(false);

export const isMobile = writable(false);

/**
 * True from Tailwind's `md` breakpoint (48rem) up: the width at which `App.svelte`'s grid shows
 * the sidebar and the desktop player bar, and every `md:hidden` / `hidden md:flex` class flips.
 *
 * `isMobile` is a different question -- it is also true on a touch screen of any width
 * (`pointer: coarse`), so a tablet in landscape is "mobile" while its CSS is already the desktop
 * layout. A component that forks in JavaScript *and* carries a `md:` class on each branch must
 * agree with the CSS, or it renders the branch the CSS hides (bug report 090: the tablet showed
 * neither the search box nor the profile button). Read this store for that fork.
 */
export const isWideLayout = readable(false, (set) => {
  if (typeof window === "undefined" || !window.matchMedia) return undefined;
  const query = window.matchMedia("(min-width: 48rem)");
  set(query.matches);
  const onChange = (event) => set(event.matches);
  query.addEventListener?.("change", onChange);
  return () => query.removeEventListener?.("change", onChange);
});
export const syncMode = writable("off"); // 'off', 'host', 'follower-jam', 'follower-radio'
persist("lms_sync_mode", syncMode);

// Radio mode (beta): the slug of the channel this client is tuned into, or
// null when radio is off. Deliberately NOT persisted -- a page reload should
// not silently start playing audio the user did not ask for.
export const radioChannel = writable(null);

// The timeline entry currently on air, as returned by /api/radio/{slug}/state.
export const radioNowPlaying = writable(null);

export const highlightedTrackId = writable(null);

export const favoriteGenres = writable([]);
persist("lms_favorite_genres", favoriteGenres);

// Favorites for the other two collection browse views. Genres came first (see
// the sync block further down); labels and playlists reuse the exact same
// mechanism so all three behave identically.
export const favoriteLabels = writable([]);
persist("lms_favorite_labels", favoriteLabels);

// Keyed by playlist id rather than name: playlist names are not unique.
export const favoritePlaylists = writable([]);
persist("lms_favorite_playlists", favoritePlaylists);

export const deduplicateEnabled = writable(true);
persist("lms_deduplicate_enabled", deduplicateEnabled);

// Whether the memories carousel is shown on the home screen. The Memories view itself is always
// reachable from the sidebar, so switching this off only removes the teaser.
export const memoriesOnHomeEnabled = writable(true);
persist("lms_memories_on_home_enabled", memoriesOnHomeEnabled);

// How many tracks a list asks for per request. Bigger means fewer round trips and
// a longer wait for the first screenful; smaller means the list appears sooner and
// scrolls into more requests. Which of those is the better trade depends on the
// connection, so it is the listener's call rather than a constant.
export const TRACK_PAGE_SIZES = [25, 50, 100, 200, 500];
export const DEFAULT_TRACK_PAGE_SIZE = 50;

export const trackPageSize = writable(DEFAULT_TRACK_PAGE_SIZE);
persist("lms_track_page_size", trackPageSize);

// How many history entries this session pushed itself. A back control can only
// honestly go back when there is somewhere of ours to return to: arriving straight
// on /management/config from a bookmark leaves nothing behind, and history.back()
// would then walk out of the app entirely.
export const pushedHistoryEntries = writable(0);

export const activeModal = writable(null); // { type, data }

// The phone's full-screen Now Playing overlay, opened from a tap on the mini
// player. Deliberately not persisted, like the other overlay flags above -- a
// reload should land on whatever page it lands on, not re-open on top of it.
export const nowPlayingOpen = writable(false);

/**
 * Opens Now Playing and pushes a history entry for it, so a browser/shell back
 * press closes the overlay instead of leaving the page underneath. Mirrors the
 * view-path effect in `App.svelte`, which does the same for a real navigation.
 */
export function openNowPlaying() {
  nowPlayingOpen.set(true);
  window.history.pushState({}, "");
  pushedHistoryEntries.update((n) => n + 1);
}

/** Upper bound on how long `closeNowPlaying` waits for its `popstate`. */
export const NOW_PLAYING_CLOSE_TIMEOUT_MS = 400;

/**
 * Closes Now Playing: the chevron, a swipe on the cover, and the shell/browser
 * back button all call this.
 *
 * The store flips straight away, so the view closes the instant any of those
 * fires rather than waiting on a `popstate` round-trip. When opening it also
 * pushed a history entry (the normal case), that entry is still there and has
 * to be consumed or the next back press hits it for no visible reason -- so
 * this also calls `history.back()`, purely to balance the stack. By the time
 * that `popstate` actually arrives, `nowPlayingOpen` already reads `false`, so
 * the listener in `App.svelte` takes its ordinary branch instead of closing
 * anything a second time; it still does the one thing that matters there,
 * decrementing `pushedHistoryEntries` to match. See `SidebarHeader.svelte` for
 * the same back-consuming pattern used for a real navigation entry.
 *
 * The returned promise settles once that `popstate` has been handled (or at
 * once, when there was no entry to consume). A caller that navigates straight
 * after closing -- a genre chip, the album, an artist -- has to wait for it:
 * `history.back()` is asynchronous, so a navigation pushed before it lands is
 * followed by a `popstate` for the entry underneath, and `App.svelte` then
 * restores the page the player was opened over. That is how every tap on a
 * genre or label chip on this screen used to end up back where it started.
 * `NOW_PLAYING_CLOSE_TIMEOUT_MS` bounds the wait for a WebView that never
 * delivers the event.
 *
 * @returns {Promise<void>}
 */
export function closeNowPlaying() {
  nowPlayingOpen.set(false);
  if (get(pushedHistoryEntries) <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    let timer = null;
    const settle = () => {
      window.removeEventListener("popstate", settle);
      clearTimeout(timer);
      resolve();
    };
    // Registered after `App.svelte`'s own listener, so it runs after that one
    // has already applied the entry's state and balanced the counter.
    window.addEventListener("popstate", settle);
    timer = setTimeout(settle, NOW_PLAYING_CLOSE_TIMEOUT_MS);
    window.history.back();
  });
}

export const visibleSortOptions = writable({
  songs: ["recent", "added", "mostplayed", "recentlyplayed", "rating", "alpha", "random"],
  albums: ["newest", "recent", "alphabeticalByName", "alphabeticalByArtist", "random", "starred"],
  artists: ["alphabetical", "trackCount", "newest", "recent", "starred", "random"],
});
persist("lms_visible_sort_options", visibleSortOptions);

// Labels are translation keys rather than text: this module is plain
// JavaScript, so the components that render these options are the ones that
// resolve them, which is also what makes them follow a language change.
export const allSortOptions = {
  songs: [
    { id: "recent", labelKey: "sort.recentlyReleased" },
    { id: "added", labelKey: "sort.recentlyAdded" },
    { id: "mostplayed", labelKey: "sort.mostPlayed" },
    { id: "recentlyplayed", labelKey: "sort.recentlyListened" },
    { id: "rating", labelKey: "sort.byRating" },
    { id: "alpha", labelKey: "sort.alphabetical" },
    { id: "starred", labelKey: "nav.starred" },
    { id: "random", labelKey: "sort.random" },
  ],
  albums: [
    { id: "newest", labelKey: "sort.recentlyAdded" },
    { id: "recent", labelKey: "sort.recentlyPlayed" },
    { id: "alphabeticalByName", labelKey: "sort.alphabeticalByTitle" },
    { id: "alphabeticalByArtist", labelKey: "sort.alphabeticalByArtist" },
    { id: "random", labelKey: "sort.random" },
    { id: "starred", labelKey: "nav.starred" },
  ],
  artists: [
    { id: "alphabetical", labelKey: "sort.alphabetical" },
    { id: "trackCount", labelKey: "sort.trackCount" },
    { id: "newest", labelKey: "sort.recentlyAdded" },
    { id: "recent", labelKey: "sort.recentlyUpdated" },
    { id: "starred", labelKey: "nav.starred" },
    { id: "random", labelKey: "sort.random" },
  ],
};

/**
 * Derived store that computes Subsonic authentication parameters.
 * Returns a query string with username, password, and client info.
 */
export const authParams = derived([credentials, subsonicToken], ([$c, $token]) => {
  if (!$c.username || !$c.password) return "";
  // The token only signs for the name it was issued to: LMS compares login names byte for byte
  // (bug report 074), and a token left over from another account must never sign for this one.
  if ($token?.token && $token.username === $c.username) {
    return subsonicTokenQuery($c.username, $token.token, sessionSaltFor($token.token));
  }
  // No token yet (a server without the endpoint, or the fetch failed): the password, as before.
  return `u=${encodeURIComponent($c.username)}&p=${encodeURIComponent($c.password)}&v=1.12.0&c=spotify&f=json`;
});

/**
 * Asks MuMa for the signed-in user's Subsonic token and stores it, so
 * `authParams` signs with it from then on. Needs the user's own MuMa key. A
 * server without the endpoint, an account LMS does not know yet, or an outage
 * leaves the stored token as it was -- the password stays the fallback until a
 * fetch succeeds. The token is never logged.
 *
 * One plain request, deliberately not `gatedFetch`: that retries a 503 for
 * several seconds, and the sign-in waits on this call. A token that is not
 * there now is asked for again at the next start.
 *
 * @param {typeof fetch} [fetchImpl] - Injected by the tests.
 * @param {string} [apiKey] - The key to ask with; the stored one by default.
 *   The sign-in passes the key of the session it has not published yet.
 * @returns {Promise<{username: string, token: string}|null>} The token, or null.
 */
export async function refreshSubsonicToken(fetchImpl = undefined, apiKey = undefined) {
  const key = apiKey ?? get(mumaApiKey);
  if (!key) return null;
  try {
    const call = fetchImpl ?? fetch;
    const response = await call(`${get(mumaApiUrl)}/api/auth/subsonic-token`, {
      headers: { "X-API-Key": key },
    });
    if (!response.ok) return null;
    const data = await response.json();
    if (
      typeof data?.token !== "string" ||
      !data.token ||
      typeof data.username !== "string" ||
      !data.username
    ) {
      return null;
    }
    const answer = { username: data.username, token: data.token };
    const current = get(subsonicToken);
    if (current.username !== answer.username || current.token !== answer.token)
      subsonicToken.set(answer);
    return answer;
  } catch (error) {
    console.warn("Could not fetch the Subsonic token", error?.name ?? "error");
    return null;
  }
}

// Whether the logged-in user has the Subsonic adminRole. `null` means "not
// determined yet" (checking, or not logged in), `true`/`false` once known.
// Centralized here (instead of every component doing its own /rest/getUser
// call) so the player/beheer toggle and the management view can be gated
// consistently. Automatically re-checked whenever the credentials change.
//
// This is only HALF the story: it only ever reflects Subsonic's own
// `adminRole`, which is never set for users who signed in via Google (they
// never populate `credentials` at all -- see AuthOverlay.svelte's
// `handleGoogleResponse`, which only sets `mumaUser`/`userPermissions`).
// `isAdmin` below combines this with the RBAC role coming from `mumaUser`
// (set by both Subsonic+MuMa login and Google login) so admins are
// recognized regardless of which login method they used.
const subsonicIsAdmin = writable(null);

/**
 * Fetches the current user's Subsonic adminRole and updates the
 * `subsonicIsAdmin` store accordingly.
 *
 * @param {{username: string, password: string}} creds - The credentials to check.
 */
async function checkAdminStatus(creds) {
  try {
    const params = get(authParams);
    if (!params) return;
    const resp = await fetch(
      restUrl(`/rest/getUser?${params}&username=${encodeURIComponent(creds.username)}`),
    );
    const data = await resp.json();
    subsonicIsAdmin.set(data["subsonic-response"]?.user?.adminRole === true);
  } catch (e) {
    console.error("Kon adminstatus niet bepalen", e);
    subsonicIsAdmin.set(false);
  }
}

let lastAdminCheckKey = null;
credentials.subscribe(($c) => {
  const key = $c.username && $c.password ? `${$c.username}:${$c.password}` : null;
  if (key === lastAdminCheckKey) return;
  lastAdminCheckKey = key;
  if (key) {
    subsonicIsAdmin.set(null);
    checkAdminStatus($c);
  } else {
    subsonicIsAdmin.set(false);
  }
});

// `mumaUser`/`userPermissions` are intentionally NOT persisted (unlike
// `mumaApiKey`), so after a page reload a Google-only user (no Subsonic
// credentials, see above) would have a `null` `mumaUser` until they happen
// to open the management view (which re-fetches it, see Management.svelte's
// onMount). Re-hydrate it here too, from the persisted `mumaApiKey`, so
// `isAdmin` (and the "Beheer" nav entry) resolves correctly right after
// startup, not only once already inside the management view.
export const mumaUserHydrated = writable(!get(mumaApiKey));

/**
 * Ends a session that holds a system key instead of a user's own key, so the
 * user signs in once more and gets their own.
 *
 * No web login hands out a system key any more: LMS's `/muma/api/auth/login`
 * used to answer every user with LMS's own `api-key`, which MuMa verifies as
 * `type: "system"` -- an always-allowed superuser, so this app made every
 * holder an admin. MuMa's login answers with the user's own key. A system key
 * still in this browser's storage is therefore a leftover from that login, and
 * it is neither trusted as an admin nor kept: the whole session goes, exactly
 * like one the server rejected, and the login page comes back.
 */
export function endLeftoverSharedKeySession() {
  endRejectedSession();
}

/**
 * Re-reads the account behind the persisted `mumaApiKey` at startup: publishes
 * the user and their permissions for a user key, drops a key the server
 * rejects, and ends the session for a leftover system key
 * (`endLeftoverSharedKeySession`). A server that cannot be reached leaves
 * everything as it was.
 *
 * @returns {Promise<void>}
 */
export async function hydrateMumaUserFromApiKey() {
  const key = get(mumaApiKey);
  if (!key) return;
  try {
    const res = await gatedFetch(`${get(mumaApiUrl)}/api/auth/verify`, {
      headers: { "X-API-Key": key },
    });
    if (!res.ok && (res.status === 401 || res.status === 403)) {
      // The backend does not accept this key any more -- a rotated or
      // no-longer-resolving system key, or an account whose key was reissued.
      // Keeping it makes every later call fail with no way back: the login
      // paths (AuthOverlay, LoginPage, Management's auto-login) only run when
      // there is no key at all, so a user would have to clear localStorage by
      // hand. A 5xx or a thrown request is NOT evidence of a bad key and
      // deliberately leaves it alone.
      mumaApiKey.set("");
      mumaUser.set(null);
      userPermissions.set([]);
    } else if (res.ok) {
      const data = await res.json();
      if (data.type === "user") {
        userPermissions.set(data.user.permissions || []);
        mumaUser.set(data.user);
        // A session persisted by a build that signed with the password picks its token up here.
        if (get(credentials).password) refreshSubsonicToken();
      } else if (data.type === "system") {
        endLeftoverSharedKeySession();
      }
    }
  } catch (e) {
    console.warn("Kon gebruikersgegevens niet verversen bij opstarten", e);
  } finally {
    mumaUserHydrated.set(true);
  }
}
hydrateMumaUserFromApiKey();

// Syncs the settings a user should find again on their other devices --
// `favoriteGenres` and the interface language -- with their account, via the
// generic per-user app-settings endpoint (`app_id = 'frontend'`), instead of
// leaving them stuck in this browser's `localStorage`. See
// docs/designs/favorite-genres/ and docs/designs/i18n/.

const frontendSettingsUrl = (userId) => `${get(mumaApiUrl)}/api/users/${userId}/settings/frontend`;

/**
 * Reads `userId`'s `frontend` blob and reports whether the read itself succeeded -- the
 * distinction {@link loadFrontendSettings} folds into `null`. A writer needs it: "the account has
 * nothing saved" may be written over, "the account could not be read" may not, because writing
 * then would replace every key this browser did not happen to change.
 *
 * A stored blob that is not valid JSON counts as read and empty: there is nothing left in it to
 * preserve, and refusing to write would leave the account stuck on it forever.
 *
 * @param {number} userId
 * @returns {Promise<{ok: boolean, settings: Object|null}>}
 */
async function readFrontendSettings(userId) {
  let data;
  try {
    const res = await gatedFetch(frontendSettingsUrl(userId), {
      headers: { "X-API-Key": get(mumaApiKey) },
    });
    if (!res.ok) return { ok: false, settings: null };
    data = await res.json();
  } catch (e) {
    console.warn("Could not load the account settings", e);
    return { ok: false, settings: null };
  }
  if (!data?.settings) return { ok: true, settings: null };
  try {
    const parsed = JSON.parse(data.settings);
    const isObject = parsed !== null && typeof parsed === "object" && !Array.isArray(parsed);
    return { ok: true, settings: isObject ? parsed : null };
  } catch (e) {
    console.warn("The stored account settings are not valid JSON", e);
    return { ok: true, settings: null };
  }
}

/**
 * Reads `userId`'s `frontend` app-settings blob.
 *
 * @param {number} userId
 * @returns {Promise<Object|null>} The parsed settings, or `null` when the
 *   account has none saved yet or the account can't be reached -- callers
 *   keep working off their local value rather than surfacing an error.
 */
export async function loadFrontendSettings(userId) {
  return (await readFrontendSettings(userId)).settings;
}

// Account-setting writes. The `frontend` blob is one JSON document shared by every key, and every
// device signed in to the account writes it: this browser, the app on a phone and on a tablet. So
// only the keys that changed are sent, with a per-key `PATCH` the server merges into the stored
// blob under a row lock (docs/designs/account-settings-merge/, bug report 116): two devices that
// change different keys at the same moment both keep their change. Changes are still queued and
// flushed together after a short debounce, so a burst of edits is one request, not one per key.

/** How long a change waits for company before it is written. */
const SETTINGS_SAVE_DELAY_MS = 400;
/** How long a write that could not read or save the blob waits before it tries again. */
const SETTINGS_RETRY_DELAY_MS = 10000;
/** `userId -> {key: value}`: the changes not yet on that account. */
const pendingSettingWrites = new Map();
let settingsFlushTimer = null;
// Flushes run one after another, never overlapping, so two writes of the same key from this
// browser always land in the order they were made.
let settingsFlushChain = Promise.resolve();
// Bumped by resetSessionState, so a write already in flight at logout does not re-queue its
// changes for an account nobody is signed in to any more.
let settingsGeneration = 0;

/**
 * Arms (or re-arms) the single flush timer.
 *
 * @param {number} delayMs
 */
function scheduleSettingsFlush(delayMs) {
  clearTimeout(settingsFlushTimer);
  settingsFlushTimer = setTimeout(() => {
    settingsFlushTimer = null;
    flushFrontendSettings();
  }, delayMs);
}

/**
 * Queues one key for `userId`'s blob and arms the debounced flush. A later value for the same key
 * replaces the queued one; different keys are written together.
 *
 * @param {number} userId
 * @param {string} key
 * @param {any} value
 */
function queueFrontendSetting(userId, key, value) {
  const pending = pendingSettingWrites.get(userId) ?? {};
  pending[key] = value;
  pendingSettingWrites.set(userId, pending);
  scheduleSettingsFlush(SETTINGS_SAVE_DELAY_MS);
}

/**
 * Writes `changes` into `userId`'s blob as a per-key `PATCH`: the server sets exactly these keys
 * and leaves every other key -- including ones another device just wrote -- as it stored them.
 *
 * A server that predates the `PATCH` answers 405; then, and only then, this falls back to
 * {@link writeWholeSettingsBlob}, the read-merge-write it replaced.
 *
 * @param {number} userId
 * @param {Object} changes
 * @returns {Promise<boolean>} Whether the account now holds the changes.
 */
async function writeSettingsBlob(userId, changes) {
  try {
    const res = await gatedFetch(frontendSettingsUrl(userId), {
      method: "PATCH",
      headers: { "X-API-Key": get(mumaApiKey), "Content-Type": "application/json" },
      body: JSON.stringify({ set: changes }),
    });
    if (res.status === 405) return writeWholeSettingsBlob(userId, changes);
    return res.ok;
  } catch (e) {
    console.warn("Could not save the account settings", e);
    return false;
  }
}

/**
 * The pre-`PATCH` write, kept for a server that does not have it yet: reads the whole blob,
 * merges `changes` in and posts the result back. Refuses to write when the read failed, since the
 * blob it would write back would be missing every key it could not see. Another device's write
 * between the read and the post is lost -- the race the `PATCH` exists to close.
 *
 * @param {number} userId
 * @param {Object} changes
 * @returns {Promise<boolean>} Whether the account now holds the changes.
 */
async function writeWholeSettingsBlob(userId, changes) {
  const current = await readFrontendSettings(userId);
  if (!current.ok) return false;
  try {
    const res = await gatedFetch(frontendSettingsUrl(userId), {
      method: "POST",
      headers: { "X-API-Key": get(mumaApiKey), "Content-Type": "application/json" },
      body: JSON.stringify({
        settings: JSON.stringify({ ...current.settings, ...changes }),
      }),
    });
    return res.ok;
  } catch (e) {
    console.warn("Could not save the account settings", e);
    return false;
  }
}

/**
 * Writes everything queued, one account at a time. Changes that could not be written go back in
 * the queue -- under anything queued meanwhile, which is newer -- and a retry is armed.
 *
 * @returns {Promise<void>}
 */
async function writePendingSettings() {
  const generation = settingsGeneration;
  let failed = false;
  for (const [userId, changes] of [...pendingSettingWrites]) {
    pendingSettingWrites.delete(userId);
    const saved = await writeSettingsBlob(userId, changes);
    if (!saved && generation === settingsGeneration) {
      pendingSettingWrites.set(userId, { ...changes, ...pendingSettingWrites.get(userId) });
      failed = true;
    }
  }
  if (failed && !settingsFlushTimer) scheduleSettingsFlush(SETTINGS_RETRY_DELAY_MS);
}

/**
 * Writes every queued account-setting change now instead of after its debounce, and resolves once
 * that attempt is over. Never rejects: a failed write stays queued and is retried.
 *
 * @returns {Promise<void>}
 */
export function flushFrontendSettings() {
  clearTimeout(settingsFlushTimer);
  settingsFlushTimer = null;
  settingsFlushChain = settingsFlushChain.then(writePendingSettings);
  return settingsFlushChain;
}

/**
 * Saves a single key into `userId`'s `frontend` app-settings blob right away, together with
 * anything else queued; every other key in the blob is left alone. Resolves once the attempt is
 * over; a failure is kept and retried rather than thrown.
 *
 * @param {number} userId
 * @param {string} key
 * @param {any} value
 * @returns {Promise<void>}
 */
export function saveFrontendSetting(userId, key, value) {
  const pending = pendingSettingWrites.get(userId) ?? {};
  pending[key] = value;
  pendingSettingWrites.set(userId, pending);
  return flushFrontendSettings();
}

let syncedUserId = null;
// True while values just fetched from the account are being applied to the
// stores, so those writes don't get echoed straight back to the server.
let applyingAccountSettings = false;

// The favorite lists that follow the account, as `settings key -> store`. They
// are handled as a group so that adding one (labels, playlists) is a one-line
// change instead of another copy of the load/save/logout plumbing.
const syncedFavoriteLists = {
  favoriteGenres,
  favoriteLabels,
  favoritePlaylists,
};

/**
 * Every store built by {@link accountSetting}, keyed by the same string the account's `frontend`
 * blob uses. Populated by each call below the account-setting stores are declared with; a plain
 * array rather than an object because two settings sharing a key would be a bug worth a duplicate
 * entry surfacing, not a silent overwrite.
 *
 * @type {Array<{key: string, store: import('svelte/store').Writable}>}
 */
const accountSettingStores = [];

/**
 * Creates one account-level setting: a writable persisted to localStorage under `lms_${key}` (so
 * it survives a reload before any account is known, same as every other store above) and, once a
 * user is signed in, synced to that account's `frontend` settings blob under `key` -- the same
 * plumbing `trackPageSize` above hand-wrote, generalised so a new setting is one call instead of
 * another copy of it. Registered in {@link accountSettingStores} so {@link applyAccountSettings}
 * picks it up too.
 *
 * Like `trackPageSize`, a value is only ever read from the account, never seeded from whatever the
 * store defaulted to locally: an account that has never chosen has not chosen, and writing the
 * default back would make every login look like a deliberate pick.
 *
 * @param {string} key
 * @param {any} defaultValue
 * @returns {import('svelte/store').Writable}
 */
function accountSetting(key, defaultValue) {
  const store = writable(defaultValue);
  persist(`lms_${key}`, store);
  accountSettingStores.push({ key, store });

  store.subscribe(($value) => {
    if (applyingAccountSettings || !syncedUserId) return;
    queueFrontendSetting(syncedUserId, key, $value);
  });
  return store;
}

// Ported from the Kotlin device-settings screen (see docs/designs/universal-ui/functional.md,
// "Device settings"): these used to be a per-phone SharedPreferences value and are now a
// per-account one, so they follow a login to the web and to a second phone alike.
// home_mode_memories is not among these: memoriesOnHomeEnabled above already covers it and
// predates this change.
export const homeShortcutCount = accountSetting("homeShortcutCount", 8);
export const homeListCount = accountSetting("homeListCount", 5);
export const separateHomeHistory = accountSetting("separateHomeHistory", true);
export const homeModeReleaseRadar = accountSetting("homeModeReleaseRadar", "BUTTON");
export const homeModeDailyMix = accountSetting("homeModeDailyMix", "BUTTON");
export const homeCountDailyMix = accountSetting("homeCountDailyMix", 2);
export const homeModeFavorites = accountSetting("homeModeFavorites", "OFF");
export const homeCountFavorites = accountSetting("homeCountFavorites", 4);
export const homeModeShortcuts = accountSetting("homeModeShortcuts", "OVERVIEW");
export const homeModeRecentlyReleased = accountSetting("homeModeRecentlyReleased", "OVERVIEW");
export const homeModeRecentlyAdded = accountSetting("homeModeRecentlyAdded", "OVERVIEW");

// "Weergave" (display). canonical_only is not among these: deduplicateEnabled above already
// covers it (one row per song version) and predates this change; it is not yet synced to the
// account the way these are.
export const showTrackNumber = accountSetting("showTrackNumber", false);
export const trackListLines = accountSetting("trackListLines", 2);
export const displayBitrateWithArtist = accountSetting("displayBitrateWithArtist", true);
export const discSort = accountSetting("discSort", false);
export const genreTrackLimit = accountSetting("genreTrackLimit", 100);

// The set-size download confirmation TrackList.svelte already shows unconditionally; this is what
// lets it be switched off. Defaults to true, not the legacy preference's false: the web has always
// confirmed here with no toggle at all, and defaulting this new one to false would silently turn
// that off for every existing user the first time this ships.
export const showConfirmationDialog = accountSetting("showConfirmationDialog", true);

// The setup steps (`setup.js`) this account has been walked through, by id. Empty means a
// first run; a step id missing from it means the step was added after the last walk-through,
// which is what makes the wizard reopen once after an update that brought a new setting.
// Kept on the account rather than the device so a second phone or the web does not start
// the tour over -- and reset on logout below so the next account on this browser gets its
// own first run.
export const setupStepsSeen = accountSetting("setupStepsSeen", []);

// True once the signed-in account's settings have been read into the stores above (or
// once it is known there is no account to read: a Subsonic-only session, a logout). The
// setup wizard waits for this before deciding it has never been shown: judging from the
// local default alone would reopen it on every new device an account signs in to.
export const accountSettingsSynced = writable(false);

/**
 * Applies `userId`'s account settings to the local stores. Anything the
 * account doesn't have yet is uploaded from the local value instead, so a
 * pre-existing local-only choice isn't lost the first time this user logs in
 * after the feature shipped.
 *
 * @param {number} userId
 */
async function applyAccountSettings(userId) {
  const settings = await loadFrontendSettings(userId);

  for (const { key, store } of accountSettingStores) {
    if (settings && key in settings) {
      applyingAccountSettings = true;
      store.set(settings[key]);
      applyingAccountSettings = false;
    }
  }

  for (const [key, store] of Object.entries(syncedFavoriteLists)) {
    if (settings && Array.isArray(settings[key])) {
      applyingAccountSettings = true;
      store.set(settings[key]);
      applyingAccountSettings = false;
    } else {
      const local = get(store);
      if (local.length > 0) {
        queueFrontendSetting(userId, key, local);
      }
    }
  }

  if (settings && typeof settings.language === "string") {
    applyingAccountSettings = true;
    setLocaleFromAccount(settings.language);
    applyingAccountSettings = false;
  } else {
    queueFrontendSetting(userId, "language", currentLocale());
  }

  // Only read, never seeded: an account without a page size has not chosen one, and
  // writing the default back would make every login look like a deliberate choice.
  if (settings && TRACK_PAGE_SIZES.includes(settings.trackPageSize)) {
    applyingAccountSettings = true;
    trackPageSize.set(settings.trackPageSize);
    applyingAccountSettings = false;
  }

  // Whatever the loops above uploaded goes out as one write, not one per key.
  if (pendingSettingWrites.has(userId)) await flushFrontendSettings();
}

mumaUser.subscribe(($user) => {
  if ($user === null) {
    // Real logout (see ProfileButton.svelte's handleLogout): don't leak this
    // account's favorites or language to whoever uses this browser next.
    if (syncedUserId !== null) {
      syncedUserId = null;
      applyingAccountSettings = true;
      for (const store of Object.values(syncedFavoriteLists)) store.set([]);
      setupStepsSeen.set([]);
      resetLocaleToBrowser();
      applyingAccountSettings = false;
    }
    accountSettingsSynced.set(true);
    return;
  }
  // No `id` means an anonymous/system-key session (e.g. the shared admin
  // key used in Management.svelte) rather than a specific account -- leave
  // whatever is currently shown untouched.
  if (!$user.id) {
    accountSettingsSynced.set(true);
    return;
  }
  if ($user.id === syncedUserId) return;
  syncedUserId = $user.id;
  accountSettingsSynced.set(false);
  applyAccountSettings($user.id).finally(() => accountSettingsSynced.set(true));
});

for (const [key, store] of Object.entries(syncedFavoriteLists)) {
  store.subscribe(($value) => {
    if (applyingAccountSettings || !syncedUserId) return;
    queueFrontendSetting(syncedUserId, key, $value);
  });
}

locale.subscribe(($locale) => {
  if (applyingAccountSettings || !syncedUserId) return;
  queueFrontendSetting(syncedUserId, "language", $locale);
});

/**
 * Saves a language change that is still waiting on its debounce right now,
 * and resolves once the account has it. Nothing pending resolves at once.
 *
 * The mobile shell recreates its activity to apply a new language, which
 * reloads the WebView and kills a debounce timer with it; the account then
 * still holds the previous language and `applyAccountSettings` puts it back on
 * the reload, so the pick appears to do nothing but refresh the screen.
 * `LanguageSetting` awaits this before telling the shell.
 *
 * @returns {Promise<void>}
 */
export async function flushLocaleSave() {
  // The language shares the one settings queue, so flushing it flushes whatever else is waiting
  // too -- which the reload that follows would otherwise lose just the same.
  await flushFrontendSettings();
}

trackPageSize.subscribe(($size) => {
  if (applyingAccountSettings || !syncedUserId) return;
  queueFrontendSetting(syncedUserId, "trackPageSize", $size);
});

/**
 * Puts everything a signed-in person leaves behind in this browser back to how a fresh visit
 * finds it: every store registered with {@link persist} (except the few marked `device`) is set
 * back to the value it was declared with and dropped from localStorage, and account-setting writes
 * still waiting are discarded, so none of them lands on the account after it signed out. Built
 * from the `persist()` registrations rather than a hand-kept list, so a store added later is
 * covered without anyone remembering to add it here.
 *
 * Call it after `mumaUser` is null -- that is what resets an account's language -- as
 * ProfileButton's logout does.
 */
export function resetSessionState() {
  settingsGeneration += 1;
  pendingSettingWrites.clear();
  clearTimeout(settingsFlushTimer);
  settingsFlushTimer = null;
  syncedUserId = null;

  applyingAccountSettings = true;
  try {
    for (const { key, store, initial, device, cancel } of persistedStores) {
      if (device) continue;
      store.set(JSON.parse(initial));
      // A throttled store may still hold a trailing write of the value just replaced.
      cancel();
      localStorage.removeItem(key);
    }
    // Not persisted, but still the previous person's until the page reloads.
    queueSource.set(null);
    feedContinuation.set(null);
    currentPlaylist.set(null);
    isPlaying.set(false);
    radioChannel.set(null);
    radioNowPlaying.set(null);
    // The language is not reset here: `mumaUser.set(null)` already puts an account's language
    // back to the browser's, and a Subsonic-only session never had one of its own.
  } finally {
    applyingAccountSettings = false;
  }
}

export const isAdmin = derived(
  [subsonicIsAdmin, mumaUser, mumaUserHydrated],
  ([$subsonicIsAdmin, $mumaUser, $mumaUserHydrated]) => {
    if ($subsonicIsAdmin === true) return true;
    if ($mumaUser && ($mumaUser.is_admin || $mumaUser.role_name === "admin")) return true;
    if ($subsonicIsAdmin === null) return null;
    if (!$mumaUserHydrated) return null;
    return false;
  },
);
