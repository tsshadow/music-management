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
 * The shell's window-mode word, or `full` for anything it does not know.
 *
 * @param {unknown} mode
 * @returns {import('../index.js').WindowMode}
 */
function windowModeOf(mode) {
  return mode === "split" || mode === "pip" ? mode : "full";
}

/**
 * Builds the shell's system implementation.
 *
 * @param {object} plugin - The registered `MumaSystem` plugin.
 * @returns {object} An implementation of the `platform.system` interface.
 */
export function createCapacitorSystem(plugin) {
  let servers = { subsonic: "", mumaApi: "", configured: true };

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
     * @returns {{subsonic: string, mumaApi: string, configured: boolean}}
     */
    serverUrl() {
      return { ...servers };
    },

    /**
     * Reads the server address the phone stores and caches it.
     *
     * Called from the shell boot path before the first request, and again after the first-run
     * screen stored an address. `configured` is false while none is stored (a fresh install,
     * issue #192); a shell from before that answer reads as configured.
     *
     * @returns {Promise<{subsonic: string, mumaApi: string, configured: boolean}>}
     */
    async loadServerUrl() {
      const answer = await plugin.serverUrl();
      servers = {
        subsonic: trimTrailingSlash(answer?.subsonic),
        mumaApi: trimTrailingSlash(answer?.mumaApi),
        configured: answer?.configured !== false,
      };
      return { ...servers };
    },

    /**
     * Asks the phone whether a MuMa server answers at `url`. The check is native: a `fetch` from
     * the WebView's origin is refused by a server without CORS headers for it.
     *
     * @param {string} url What the listener typed.
     * @returns {Promise<ServerAddressCheck>}
     */
    async checkServerAddress(url) {
      const answer = await plugin.checkServerAddress({ url });
      return {
        state: answer?.state ?? "unreachable",
        url: answer?.url ?? "",
        subsonic: trimTrailingSlash(answer?.subsonic),
        mumaApi: trimTrailingSlash(answer?.mumaApi),
        buildServer: answer?.buildServer === true,
      };
    },

    /**
     * Stores the server address and makes the phone use it. `signOut` ends the session and
     * drops the old server's cache first; pass it for another server, not for another spelling
     * of the same one. Rejects with code `invalid` or `insecure`.
     *
     * @param {{url: string, signOut: boolean}} request
     * @returns {Promise<void>}
     */
    async setServerAddress({ url, signOut }) {
      await plugin.setServerAddress({ url, signOut: signOut === true });
    },

    /**
     * The address a first run suggests: the build's own server, or `""` when the build has
     * none.
     *
     * @returns {Promise<string>}
     */
    async suggestedServerAddress() {
      try {
        const answer = await plugin.suggestedServerAddress();
        return typeof answer?.url === "string" ? answer.url : "";
      } catch (error) {
        console.warn("Could not ask the shell for a suggested server", error);
        return "";
      }
    },

    /**
     * The session the phone holds for this server.
     *
     * `signedIn` is the phone's explicit signed-in flag. It replaced the blank
     * password that used to mean "logged out": the phone no longer stores the
     * password or hands it over (issue #101). `mumaApiKey` is what the web
     * takes the session over with.
     *
     * `subsonicToken`/`subsonicTokenUser` are the Subsonic token the native client signs with and
     * the login name it was issued for, blank while the phone has none: the web signs with the
     * same token instead of fetching its own, and without one sends no Subsonic request at all
     * (issue #72).
     *
     * @returns {Promise<{username: string, signedIn: boolean, clientId: string,
     *   serverId: number, mumaApiKey?: string, mumaUserId?: number,
     *   subsonicToken: string, subsonicTokenUser: string}>}
     */
    async credentials() {
      const answer = await plugin.credentials();
      return {
        username: answer?.username ?? "",
        signedIn: answer?.signedIn === true,
        clientId: answer?.clientId ?? "",
        serverId: answer?.serverId ?? 0,
        mumaApiKey: answer?.mumaApiKey ?? "",
        mumaUserId: answer?.mumaUserId ?? 0,
        subsonicToken: answer?.subsonicToken ?? "",
        subsonicTokenUser: answer?.subsonicTokenUser ?? "",
      };
    },

    /**
     * Ends the session on the phone: clears the signed-in flag, the muma API key/user id and
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
     * Whether this APK can do "Sign in with Google" natively: a real Web client ID was compiled
     * in and the stored address is the build's own server (issue #192). A bridge failure reads as "no", so the login page simply does not offer the button.
     *
     * @returns {Promise<boolean>}
     */
    async googleSignInAvailable() {
      try {
        const answer = await plugin.googleSignInAvailable();
        return answer?.available === true;
      } catch (error) {
        console.warn("Could not ask the shell whether Google sign-in is available", error);
        return false;
      }
    },

    /**
     * Native "Sign in with Google" through Android's Credential Manager. Google refuses its web
     * sign-in inside a WebView, so the shell obtains the ID token and the page posts it to
     * `/api/auth/google` as the browser's button would (bug report 106).
     *
     * @returns {Promise<string|null>} The ID token, or `null` when the user closed the chooser.
     * @throws {Error} With `code` `not-configured`, `no-credential` or `failed`.
     */
    async googleSignIn() {
      try {
        const answer = await plugin.googleSignIn();
        return answer?.idToken || null;
      } catch (error) {
        if (error?.code === "cancelled") return null;
        throw error;
      }
    },

    /**
     * Hands the session the web login screen just started to the phone -- the account's name, its
     * MuMa API key and account id, never the password (issue #101) -- so downloads and Android
     * Auto see the same session afterwards.
     *
     * @param {{url?: string, username: string, mumaApiKey: string, mumaUserId?: number}} creds
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
     * `keepOn` is sent only when the caller passed it, and the lock-screen flags only when the
     * caller passed one of them or no `keepOn`: the shell applies what it is sent, so the car
     * screen and the split screen cannot undo each other's flags.
     *
     * @param {{showWhenLocked?: boolean, turnScreenOn?: boolean, keepOn?: boolean}} flags
     * @returns {Promise<void>}
     */
    async setKeepScreenOn(flags) {
      const asked = flags ?? {};
      const message = {};
      if ("showWhenLocked" in asked || "turnScreenOn" in asked || !("keepOn" in asked)) {
        message.showWhenLocked = asked.showWhenLocked === true;
        message.turnScreenOn = asked.turnScreenOn === true;
      }
      if ("keepOn" in asked) message.keepOn = asked.keepOn === true;
      await plugin.setKeepScreenOn(message);
    },

    /**
     * The window the app is in now. Anything but `split` or `pip` reads as `full`, so a
     * malformed answer never shows the compact player.
     *
     * @returns {Promise<{mode: import('../index.js').WindowMode}>}
     */
    async windowMode() {
      const answer = await plugin.windowMode();
      return { mode: windowModeOf(answer?.mode) };
    },

    /**
     * Split screen or the floating window started or ended.
     *
     * @param {function(import('../index.js').WindowMode): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onWindowModeChanged(handler) {
      return listen(plugin, "windowModeChanged", (event) => handler(windowModeOf(event?.mode)));
    },

    /**
     * Whether Google Maps is installed and can open next to the app.
     *
     * @returns {Promise<{value: boolean}>}
     */
    async canNavigate() {
      const answer = await plugin.canNavigate();
      return { value: answer?.value === true };
    },

    /**
     * Opens Google Maps next to the app. Rejects when it does not open.
     *
     * @returns {Promise<void>}
     */
    async navigateAdjacent() {
      await plugin.navigateAdjacent();
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

    /**
     * Hands a PNG to the Android share sheet. The plugin writes it to the app's cache and offers
     * it through the FileProvider; it resolves once the chooser opened. A rejection (the image
     * could not be written) reaches the caller.
     *
     * @param {{dataUrl: string, title: string, fileName: string}} image
     * @returns {Promise<'shared'>}
     */
    async share({ dataUrl, title, fileName }) {
      await plugin.share({ dataUrl, title, fileName });
      return "shared";
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
