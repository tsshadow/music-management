import { listen, fireAndForget } from "./listen.js";

/**
 * `platform.system` inside the Android shell.
 *
 * Three of its members exist only here, and each one answers a question the
 * browser never has to ask: which server is this phone signed in to, what are
 * its credentials, and did the user just press the system back button.
 *
 * ### The server bases are cached on purpose
 *
 * `serverUrl()` is synchronous in the contract -- `store.js` reads it while
 * building a URL -- and a bridge call is not. So the shell's boot path calls
 * `loadServerUrl()` once, before anything fetches, and every later reader gets
 * the cached pair. Until that has happened both bases are the empty string,
 * which means "same origin": inside the shell that is `https://localhost`, so a
 * request made before the boot path finished fails loudly instead of quietly
 * reaching the wrong server.
 *
 * ### The back protocol
 *
 * The activity emits `back` with a sequence number and gives the web UI 350 ms
 * to say it used the press; if it does not, the activity finishes. The claim
 * therefore has to go out in the same turn the event arrived in, which is why
 * the handler passed to `onBack` must be synchronous and must return `true`
 * when it consumed the press. Anything awaited before the claim is a coin flip.
 */

/**
 * Builds the shell's system implementation.
 *
 * @param {object} plugin - The registered `MumaSystem` plugin.
 * @returns {object} An implementation of the `platform.system` interface.
 */
export function createCapacitorSystem(plugin) {
  let servers = { subsonic: "", mumaApi: "" };

  return {
    isNative: true,

    /**
     * The bases every URL is built on, as last read by {@link loadServerUrl}.
     *
     * @returns {{subsonic: string, mumaApi: string}}
     */
    serverUrl() {
      return { ...servers };
    },

    /**
     * Reads the server the phone is signed in to and caches it.
     *
     * Called once, from the shell boot path, before the first request.
     *
     * @returns {Promise<{subsonic: string, mumaApi: string}>}
     */
    async loadServerUrl() {
      const answer = await plugin.serverUrl();
      servers = {
        subsonic: trimTrailingSlash(answer?.subsonic),
        mumaApi: trimTrailingSlash(answer?.mumaApi),
      };
      return { ...servers };
    },

    /**
     * What the phone has stored for this server.
     *
     * A blank `password` is how the native app says "logged out" -- the same
     * check its own welcome screen makes -- so the boot path reads it as
     * "show the login page" rather than as a failed sign-in.
     *
     * @returns {Promise<{username: string, password: string, clientId: string,
     *   forcePlainTextPassword: boolean, serverId: number, mumaApiKey?: string,
     *   mumaUserId?: number}>}
     */
    async credentials() {
      const answer = await plugin.credentials();
      return {
        username: answer?.username ?? "",
        password: answer?.password ?? "",
        clientId: answer?.clientId ?? "",
        forcePlainTextPassword: answer?.forcePlainTextPassword === true,
        serverId: answer?.serverId ?? 0,
        mumaApiKey: answer?.mumaApiKey ?? "",
        mumaUserId: answer?.mumaUserId ?? 0,
      };
    },

    /**
     * Ends the session on the phone: clears the stored password, the muma API key/user id and
     * the muma tokens, and stops the queue the platform service was holding. Downloaded files are
     * left alone. The caller reloads afterwards -- this only has to make sure the next boot finds
     * nothing to sign back in with.
     *
     * @returns {Promise<void>}
     */
    signOut() {
      return plugin.signOut();
    },

    /**
     * Writes a username/password pair the web login screen just verified back to the phone, so
     * downloads, Android Auto and the legacy UI see the same session afterwards.
     *
     * @param {{url?: string, username: string, password: string}} creds
     * @returns {Promise<void>}
     */
    saveCredentials(creds) {
      return plugin.saveCredentials(creds);
    },

    /** Hands the phone back to the Kotlin interface and restarts into it. */
    switchToLegacyUi() {
      fireAndForget("switchToLegacyUi", plugin.switchToLegacyUi());
    },

    /** Opens the Kotlin settings screen; phase 1 keeps downloads and the car there. */
    openLegacySettings() {
      fireAndForget("openLegacySettings", plugin.openLegacySettings());
    },

    /**
     * The system back gesture.
     *
     * @param {function(): boolean} handler - Must be synchronous and must
     *   return `true` when the press was used for something -- closing a sheet,
     *   a drawer, a panel, or popping a history entry. Returning anything else
     *   lets the activity finish, which is what back at the root of an app does.
     * @returns {function(): void} Unsubscribes.
     */
    onBack(handler) {
      return listen(plugin, "back", (event) => {
        let claimed = false;
        try {
          claimed = handler() === true;
        } catch (error) {
          console.error("The back handler failed; letting the shell close", error);
        }
        // Before any await, deliberately: the activity is holding a 350 ms
        // timer and a claim that arrives after it has already finished.
        if (claimed) fireAndForget("handledBack", plugin.handledBack({ seq: event?.seq }));
      });
    },

    /**
     * A route from outside the app: the quick-settings tile, the car-mode
     * notification, a launcher shortcut or a "play from search" intent.
     *
     * @param {function(string): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onDeepLink(handler) {
      return listen(plugin, "deepLink", (event) => {
        const route = event?.route;
        if (typeof route === "string" && route) handler(route);
      });
    },

    /**
     * Whether the app is showing on a car screen.
     *
     * @param {function(boolean): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    carConnected(handler) {
      return listen(plugin, "carConnected", (event) => handler(event?.connected === true));
    },

    /**
     * The "Apparaat" settings tab's whole state in one call.
     *
     * @returns {Promise<import('../index.js').DeviceSettings>}
     */
    async getSettings() {
      return await plugin.getSettings();
    },

    /**
     * Writes one field of {@link import('../index.js').DeviceSettings}.
     *
     * @param {{key: string, value: boolean|number}} setting
     * @returns {Promise<void>}
     */
    async setSetting(setting) {
      await plugin.setSetting(setting);
    },
  };
}

/**
 * @param {string|undefined} value
 * @returns {string} The base without a trailing slash, so joining a path that
 *   starts with one cannot produce a double slash.
 */
function trimTrailingSlash(value) {
  return typeof value === "string" ? value.replace(/\/+$/, "") : "";
}
