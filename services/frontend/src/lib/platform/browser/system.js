import { get } from "svelte/store";
import { credentials, mumaApiUrl } from "../../store.js";

/**
 * Where the servers are, and the platform events the browser never sends.
 *
 * `serverUrl()` does not decide anything: the web resolves both bases exactly as
 * it always has -- `credentials.url` defaults to `window.location.origin` and
 * `mumaApiUrl` to `/muma`, both in `store.js`, both overridable per environment
 * and per user -- and this reads them back. A native shell answers the same call
 * from the server the user signed in to, which is the whole point of asking the
 * platform rather than the window.
 */

/** @type {import('../index.js').PlatformSystem} */
const system = {
  isNative: false,

  /**
   * A browser tab is not an APK and has no version of its own to report.
   *
   * @returns {Promise<string>}
   */
  async appVersion() {
    return "";
  },

  /**
   * No APK, nothing to describe.
   *
   * @returns {Promise<null>}
   */
  async appInfo() {
    return null;
  },

  /**
   * A browser tab is updated by reloading it; asking apk-hoster would be asking about somebody
   * else's build. Rejecting (rather than answering "up to date") keeps the About page's button
   * honest, and the automatic check in `appUpdate.js` never runs here in the first place.
   *
   * @returns {Promise<never>}
   */
  async checkForUpdate() {
    throw new Error("a browser tab has no APK to update");
  },

  /**
   * @param {string} url
   * @returns {Promise<void>}
   */
  async openUrl(url) {
    window.open(url, "_blank", "noopener");
  },

  /**
   * A browser tab has no APK assets to read muma-mobile's `CHANGELOG.md` from. `null` is what
   * keeps `mobileReleaseNotes.js`'s once-per-upgrade modal from ever showing outside the shell.
   *
   * @returns {Promise<null>}
   */
  async releaseNotes() {
    return null;
  },

  /**
   * @returns {{subsonic: string, mumaApi: string, configured: boolean}} Bases to build URLs on.
   *   Either may be an empty string, which means "same origin" -- that is what
   *   the dev server and the reverse proxy in front of production both want. A browser tab
   *   always has a server: the one that served the page.
   */
  serverUrl() {
    return { subsonic: get(credentials).url, mumaApi: get(mumaApiUrl), configured: true };
  },

  /**
   * Never called in a browser: the first-run screen is the shell's. Answers `ok` so a caller
   * that does is not stopped.
   *
   * @returns {Promise<import('../index.js').ServerAddressCheck>}
   */
  async checkServerAddress() {
    return { state: "ok", url: "", subsonic: "", mumaApi: "", buildServer: false };
  },

  /**
   * A browser tab has no address to store: its server is the page's origin.
   *
   * @returns {Promise<never>}
   */
  async setServerAddress() {
    throw Object.assign(new Error("a browser tab has no server address to store"), {
      code: "invalid",
    });
  },

  /**
   * A browser tab suggests nothing; it never shows the first-run screen.
   *
   * @returns {Promise<string>}
   */
  async suggestedServerAddress() {
    return "";
  },

  /**
   * The phone-side half of signing out. A browser tab has no native session to end -- the caller
   * clears its own stores -- so this resolves immediately.
   *
   * @returns {Promise<void>}
   */
  signOut() {
    return Promise.resolve();
  },

  /**
   * A browser tab signs in with Google through Google Identity Services on the login page itself,
   * so there is no native sign-in to offer.
   *
   * @returns {Promise<boolean>}
   */
  googleSignInAvailable() {
    return Promise.resolve(false);
  },

  /**
   * Never called in a browser (see {@link googleSignInAvailable}); rejects so a caller that does
   * gets a clear answer rather than a silent nothing.
   *
   * @returns {Promise<never>}
   */
  googleSignIn() {
    return Promise.reject(
      Object.assign(new Error("no native Google sign-in in a browser"), { code: "not-configured" }),
    );
  },

  /**
   * The phone-side half of persisting a verified sign-in. A browser tab has nowhere to write it
   * back to, so this resolves immediately.
   *
   * @param {{url?: string, username: string, mumaApiKey: string, mumaUserId?: number}} _creds
   * @returns {Promise<void>}
   */
  saveCredentials(_creds) {
    return Promise.resolve();
  },

  /**
   * The platform's own back gesture -- the Android back button, not the browser
   * history. The web has no such thing: history is the browser's and the router
   * already listens to it.
   *
   * @param {function(): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onBack(_handler) {
    return () => {};
  },

  /**
   * A link opened outside the app, as a route the router understands
   * ("album:123"). The web reaches its routes through the URL instead.
   *
   * @param {function(string): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onDeepLink(_handler) {
    return () => {};
  },

  /**
   * Whether the app is showing on a car screen. Reported on subscribe and on
   * every change; the browser reports nothing, so a subscriber keeps whatever
   * it defaulted to.
   *
   * @param {function(boolean): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  carConnected(_handler) {
    return () => {};
  },

  /**
   * What `carConnected` would have last reported. A browser tab is never in a car, so this is
   * always `{connected: false}` -- the same honest-empty answer `carConnected` gives by never
   * firing.
   *
   * @returns {Promise<{connected: boolean}>}
   */
  async carState() {
    return { connected: false };
  },

  /**
   * The lock-screen behaviour a native car screen asks for while it is on top. A browser tab has
   * no lock screen to show over, so this resolves without doing anything.
   *
   * @param {{showWhenLocked: boolean, turnScreenOn: boolean}} _flags
   * @returns {Promise<void>}
   */
  async setKeepScreenOn(_flags) {},

  /**
   * A browser tab is always a whole window to the app: the PC's floating window is its own
   * document (`miniplayerWindow.js`), not a mode of this one.
   *
   * @returns {Promise<{mode: import('../index.js').WindowMode}>}
   */
  async windowMode() {
    return { mode: "full" };
  },

  /**
   * @param {function(import('../index.js').WindowMode): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onWindowModeChanged(_handler) {
    return () => {};
  },

  /**
   * A browser tab cannot put Google Maps next to itself.
   *
   * @returns {Promise<{value: boolean}>}
   */
  async canNavigate() {
    return { value: false };
  },

  /** Nothing to open in a browser tab; `canNavigate` already said so. */
  async navigateAdjacent() {},

  /** A browser tab cannot float; the PC has its own window (`miniplayerWindow.js`). */
  async enterPictureInPicture() {},

  /**
   * The "Apparaat" settings tab has nothing to read in a browser tab -- there is no
   * native whitelist behind it -- and the tab itself never shows without `isNative`,
   * so this is never actually read.
   *
   * @returns {Promise<import('../index.js').DeviceSettings>}
   */
  async getSettings() {
    return /** @type {import('../index.js').DeviceSettings} */ ({});
  },

  /**
   * @param {{key: string, value: boolean|number|string[]}} _setting
   * @returns {Promise<void>} Resolves without writing anything.
   */
  async setSetting(_setting) {},

  /**
   * A browser has no Bluetooth pairing list to read.
   *
   * @returns {Promise<{permissionGranted: boolean, devices: Array}>}
   */
  async listBondedDevices() {
    return { permissionGranted: false, devices: [] };
  },

  /** A browser has no such permission to request. */
  requestCarModeFullScreenPermission() {},

  /**
   * A browser has no filesystem to pick a cache directory in.
   *
   * @returns {Promise<{}>}
   */
  async pickCacheLocation() {
    return {};
  },

  /** A browser has no custom cache location to clear. */
  clearCustomCacheLocation() {},

  /**
   * A browser has no native chrome to follow the pick; the web UI's own `locale` store is what
   * it reads instead.
   *
   * @param {string} _locale
   */
  setAppLocale(_locale) {},

  /**
   * A browser tab does not know where its audio goes -- there is no `AudioContext.sinkId` worth
   * naming for an `<audio>` element -- and `null` is what hides the label on the player screen.
   *
   * @returns {Promise<null>}
   */
  async outputRoute() {
    return null;
  },

  /**
   * @param {function(import('../index.js').OutputRoute): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onOutputRouteChanged(_handler) {
    return () => {};
  },

  /** A browser has no output switcher to open; the label that would open it is not shown either. */
  async openOutputPicker() {},
};

export default system;
