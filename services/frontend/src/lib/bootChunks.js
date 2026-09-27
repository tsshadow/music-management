import { get } from "svelte/store";
import { pathToState } from "./router.js";
import { activeManagementTab, activeSettingsTab, isAdmin, signedIn } from "./store.js";
import { adminNextChunks, likelyNextChunks, preloadOnIdle } from "./lazyViews.js";

/**
 * The glue between `main.js` and the lazily loaded views (issue #114): which chunks the first
 * screen needs, what to fetch once it is up, and what to do when a chunk is gone.
 */

/**
 * The view state the app will open on, as far as chunks are concerned. Mirrors what
 * `App.svelte` does on mount: signed out is the login page, which is in the main chunk;
 * `/management` and `/settings` without a tab open the tab the store remembers.
 *
 * @param {string} pathname
 * @param {{signedIn?: boolean, managementTab?: string, settingsTab?: string}} [current] -
 *   Injected by the tests.
 * @returns {{view: string, managementTab?: string, settingsTab?: string}}
 */
export function initialState(
  pathname,
  {
    signedIn: isSignedIn = get(signedIn),
    managementTab = get(activeManagementTab),
    settingsTab = get(activeSettingsTab),
  } = {},
) {
  if (!isSignedIn) return { view: "login" };
  const state = pathToState(pathname);
  if (state.view === "management" && !state.managementTab) {
    return { ...state, managementTab };
  }
  if (state.view === "settings" && !state.settingsTab) {
    return { ...state, settingsTab };
  }
  return state;
}

/**
 * Fetches the pages one tap away once the first screen is up, and Beheer's shell and first tab
 * as soon as the account turns out to be an admin -- which is often only known a moment after
 * mounting, when MuMa's user has been read.
 *
 * @param {{requestIdle?: (cb: () => void) => void, admin?: import('svelte/store').Readable<boolean|null>}} [options]
 * @returns {() => void} Stops waiting for the admin answer.
 */
export function preloadLikelyNext({ requestIdle, admin = isAdmin } = {}) {
  preloadOnIdle(likelyNextChunks(), { requestIdle });
  let done = false;
  let unsubscribe = () => {};
  unsubscribe = admin.subscribe((value) => {
    if (done || value !== true) return;
    done = true;
    preloadOnIdle(adminNextChunks(), { requestIdle });
    // Subscribing calls back synchronously, before `unsubscribe` holds the real function.
    queueMicrotask(() => unsubscribe());
  });
  return () => unsubscribe();
}

/** How long a reload for a missing chunk suppresses the next one, so a real outage never loops. */
export const CHUNK_RELOAD_WINDOW_MS = 10_000;
const RELOAD_KEY = "muma_chunk_reload_at";

/**
 * Reloads the page once when a lazily loaded chunk cannot be fetched (Vite's
 * `vite:preloadError`). That is what a browser tab left open across a deploy runs into: its
 * index.html names chunk files the new build replaced. A second failure within
 * `CHUNK_RELOAD_WINDOW_MS` is left to the view's own retry pill instead of reloading forever
 * while the server is down. Inside the Android shell the chunks are files in the APK and never
 * go missing, so this never fires there.
 *
 * @param {Window} win
 * @param {{now?: () => number}} [options] - Injected by the tests.
 */
export function installChunkReload(win, { now = () => Date.now() } = {}) {
  win.addEventListener("vite:preloadError", (event) => {
    let last = 0;
    try {
      last = Number(win.sessionStorage.getItem(RELOAD_KEY)) || 0;
    } catch {
      // Storage refused (private mode): reload anyway, the window check just cannot hold.
    }
    if (now() - last < CHUNK_RELOAD_WINDOW_MS) return;
    try {
      win.sessionStorage.setItem(RELOAD_KEY, String(now()));
    } catch {
      // See above.
    }
    event.preventDefault();
    win.location.reload();
  });
}
