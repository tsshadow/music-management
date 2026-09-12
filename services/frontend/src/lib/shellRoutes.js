/**
 * The routes the Android shell sends in, translated into what the web app does
 * about them.
 *
 * `CapacitorActivity` builds these strings from the intent extras the Kotlin app
 * has always used, so they are a cross-process contract: the quick-settings
 * tile, the car-mode notification, the launcher shortcut and a "play from
 * search" intent all arrive here. That is why the mapping is a pure function in
 * its own file rather than a switch inside `App.svelte` -- it is the part worth
 * testing, and the part that must keep working when the screens behind it move.
 */

/** The routes `CapacitorActivity.routeFor` can produce. */
export const SHELL_ROUTES = ["car", "voice", "player", "random", "search:<query>"];

/**
 * What to do about one route.
 *
 * @param {string} route - `car`, `voice`, `player`, `random` or `search:<query>`.
 * @param {{isMobile?: boolean}} [context] - `isMobile` is read from the
 *   `isMobile` store by the caller rather than imported here, so this stays a
 *   pure function of its arguments and is cheap to test for both shells.
 * @returns {{kind: 'queue'|'now-playing'|'random'|'view', view?: string, unbuilt?: string}}
 *   `queue` opens the desktop queue panel · `now-playing` opens the phone's
 *   full-screen player · `random` fills the queue with random tracks in the
 *   current mode · `view` sets `activeView`. `unbuilt` is set for a route
 *   whose screen is a later phase: it still lands somewhere usable, and the
 *   action log says which screen was asked for, which is the only way a tap
 *   that "did nothing" can be read back out of a crash report.
 */
export function deepLinkAction(route, { isMobile = false } = {}) {
  if (route === "player") return { kind: isMobile ? "now-playing" : "queue" };
  if (route === "random") return { kind: "random" };
  if (typeof route === "string" && route.startsWith("search:")) {
    const query = route.slice("search:".length).trim();
    return query ? { kind: "view", view: `search:${query}` } : { kind: "view", view: "home" };
  }
  // Car mode and the voice screen are Svelte screens in phase 4. Until they
  // exist the tap opens the app on its home screen rather than on nothing.
  if (route === "car" || route === "voice") return { kind: "view", view: "home", unbuilt: route };
  return { kind: "view", view: "home" };
}

/**
 * The request that fills the queue with random tracks.
 *
 * The same endpoint and the same mode boundary the track list uses: ten minutes
 * separates songs from sets, and a "play something" from a car or a tile has to
 * respect the mode the listener is in, or it plays four-minute tracks at the
 * exact moment they asked for a set.
 *
 * @param {{mode: string, auth: string, seed?: number, count?: number}} request
 * @returns {string} A path for `restUrl()`.
 */
export function randomTracksUrl({ mode, auth, seed = Date.now(), count = 50 }) {
  const duration = mode === "sets" ? "minDuration=10" : "maxDuration=10";
  return `/rest/getSpotifyTracks?sort=random&seed=${seed}&offset=0&count=${count}&${duration}&${auth}`;
}
