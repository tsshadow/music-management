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
     * The APK's own `versionName`, e.g. "6.35.1". See the `PlatformSystem` typedef for why this
     * is a separate call from `platform.diagnostics.identify`'s bundle version.
     *
     * @returns {Promise<string>}
     */
    async appVersion() {
      const answer = await plugin.appVersion();
      return typeof answer?.version === "string" ? answer.version : "";
    },

    /**
     * The whole `appVersion` answer, for the About page. Same bridge call as {@link appVersion};
     * the two are separate so every existing caller of the version string stays a string.
     *
     * @returns {Promise<import('../index.js').AppInfo|null>}
     */
    async appInfo() {
      const answer = await plugin.appVersion();
      if (typeof answer?.version !== "string") return null;
      return {
        version: answer.version,
        versionCode: Number(answer.versionCode ?? 0),
        buildType: String(answer.buildType ?? ""),
        packageName: String(answer.packageName ?? ""),
        androidVersion: String(answer.androidVersion ?? ""),
        device: String(answer.device ?? ""),
      };
    },

    /**
     * See the `PlatformSystem` typedef. The plugin rejects when the hoster could not be asked,
     * and that rejection is passed on as-is: the caller decides how to report it.
     *
     * @returns {Promise<import('../index.js').AppUpdateCheck>}
     */
    async checkForUpdate() {
      const answer = await plugin.checkForUpdate();
      return {
        available: answer?.available === true,
        currentVersionCode: Number(answer?.currentVersionCode ?? 0),
        currentVersionName: String(answer?.currentVersionName ?? ""),
        currentSeries: String(answer?.currentSeries ?? ""),
        latestVersionCode: Number(answer?.latestVersionCode ?? 0),
        latestVersionName: String(answer?.latestVersionName ?? ""),
        latestSeries: String(answer?.latestSeries ?? ""),
        url: String(answer?.url ?? ""),
      };
    },

    /**
     * @param {string} url
     * @returns {Promise<void>}
     */
    async openUrl(url) {
      await plugin.openUrl({ url });
    },

    /**
     * The text of muma-mobile's own `CHANGELOG.md`, read from the APK's assets. See the
     * `PlatformSystem` typedef for why this travels through the shell rather than a bundled
     * import. An empty string reads the same as no asset at all: both mean nothing to show.
     *
     * @returns {Promise<string|null>}
     */
    async releaseNotes() {
      const answer = await plugin.releaseNotes();
      return typeof answer?.text === "string" && answer.text !== "" ? answer.text : null;
    },

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
     * downloads and Android Auto see the same session afterwards.
     *
     * @param {{url?: string, username: string, password: string}} creds
     * @returns {Promise<void>}
     */
    saveCredentials(creds) {
      return plugin.saveCredentials(creds);
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
     * What `emitCarConnected` last sent, read once rather than waited for -- the bootstrap path
     * calls this before the car screen is shown so a cold start already in the car does not have
     * to wait for the plugin to feel like repeating itself.
     *
     * @returns {Promise<{connected: boolean}>}
     */
    async carState() {
      const answer = await plugin.carState();
      return { connected: answer?.connected === true };
    },

    /**
     * Asks for, or releases, the lock-screen behaviour the legacy car-mode screen got for free
     * from a navigation-destination listener.
     *
     * @param {{showWhenLocked: boolean, turnScreenOn: boolean}} flags
     * @returns {Promise<void>}
     */
    async setKeepScreenOn(flags) {
      await plugin.setKeepScreenOn({
        showWhenLocked: flags?.showWhenLocked === true,
        turnScreenOn: flags?.turnScreenOn === true,
      });
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
     * @param {{key: string, value: boolean|number|string[]}} setting
     * @returns {Promise<void>}
     */
    async setSetting(setting) {
      await plugin.setSetting(setting);
    },

    /**
     * The phone's paired Bluetooth devices, for the car-mode picker.
     *
     * @returns {Promise<{permissionGranted: boolean, devices: Array<{address: string, name:
     *   string, isCarClass: boolean}>}>}
     */
    async listBondedDevices() {
      const answer = await plugin.listBondedDevices();
      return {
        permissionGranted: answer?.permissionGranted === true,
        devices: Array.isArray(answer?.devices) ? answer.devices : [],
      };
    },

    /** Opens the "use full screen intent" permission screen for car mode. Fire-and-forget. */
    requestCarModeFullScreenPermission() {
      fireAndForget(
        "requestCarModeFullScreenPermission",
        plugin.requestCarModeFullScreenPermission(),
      );
    },

    /**
     * Opens the system's directory picker for a custom cache location.
     *
     * @returns {Promise<{uri: string, path: string}|{}>}
     */
    async pickCacheLocation() {
      return (await plugin.pickCacheLocation()) ?? {};
    },

    /** Turns a custom cache location back off. */
    clearCustomCacheLocation() {
      fireAndForget("clearCustomCacheLocation", plugin.clearCustomCacheLocation());
    },

    /**
     * Tells the shell which language the web `LanguageSetting` just picked, so the native chrome
     * follows it too. Fire-and-forget: the activity recreates itself on its own time, and the web
     * UI has already applied the pick to its own `locale` store regardless of how this resolves.
     *
     * @param {string} locale
     */
    setAppLocale(locale) {
      fireAndForget("setAppLocale", plugin.setAppLocale({ locale }));
    },

    /**
     * The output media plays through, as the Kotlin side named it. See the `PlatformSystem`
     * typedef for how the phone decides. An answer without a name or a type -- the plugin
     * resolves an empty object while it has no context to read its strings from -- is `null`,
     * the same "nothing to show" a browser tab answers.
     *
     * @returns {Promise<import('../index.js').OutputRoute|null>}
     */
    async outputRoute() {
      return outputRouteOf(await plugin.outputRoute());
    },

    /**
     * The `outputRouteChanged` event, fed by an `AudioDeviceCallback` on the Kotlin side. A
     * malformed payload is dropped rather than handed on as a route with no name.
     *
     * @param {function(import('../index.js').OutputRoute): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onOutputRouteChanged(handler) {
      return listen(plugin, "outputRouteChanged", (event) => {
        const route = outputRouteOf(event);
        if (route) handler(route);
      });
    },

    /**
     * The system output switcher, or Bluetooth settings on a build without one. Awaited rather
     * than fire-and-forget so a rejection -- neither screen exists -- reaches the caller.
     *
     * @returns {Promise<void>}
     */
    async openOutputPicker() {
      await plugin.openOutputPicker();
    },
  };
}

/** The type words the Kotlin `OutputRouteType` enum can send; anything else is not a route. */
const OUTPUT_ROUTE_TYPES = new Set(["bluetooth", "wired", "speaker", "usb", "other"]);

/**
 * @param {any} answer - A plugin answer or event payload.
 * @returns {import('../index.js').OutputRoute|null} The route, or `null` when the payload is not
 *   one -- an empty object from a plugin without a context, or a message from a build whose
 *   type words this bundle does not know.
 */
function outputRouteOf(answer) {
  if (typeof answer?.name !== "string" || answer.name === "") return null;
  if (!OUTPUT_ROUTE_TYPES.has(answer.type)) return null;
  return { name: answer.name, type: answer.type };
}

/**
 * @param {string|undefined} value
 * @returns {string} The base without a trailing slash, so joining a path that
 *   starts with one cannot produce a double slash.
 */
function trimTrailingSlash(value) {
  return typeof value === "string" ? value.replace(/\/+$/, "") : "";
}
