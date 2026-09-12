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
   * @returns {{subsonic: string, mumaApi: string}} Bases to build URLs on.
   *   Either may be an empty string, which means "same origin" -- that is what
   *   the dev server and the reverse proxy in front of production both want.
   */
  serverUrl() {
    return { subsonic: get(credentials).url, mumaApi: get(mumaApiUrl) };
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
   * The phone-side half of persisting a verified sign-in. A browser tab has nowhere to write it
   * back to, so this resolves immediately.
   *
   * @param {{url?: string, username: string, password: string}} _creds
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
   * @param {{key: string, value: boolean|number}} _setting
   * @returns {Promise<void>} Resolves without writing anything.
   */
  async setSetting(_setting) {},
};

export default system;
