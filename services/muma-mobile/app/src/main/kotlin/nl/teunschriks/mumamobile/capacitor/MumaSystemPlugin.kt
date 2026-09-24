/*
 * MumaSystemPlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.DocumentsContract
import androidx.activity.result.ActivityResult
import androidx.core.app.ActivityCompat
import androidx.core.net.toUri
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.car.CAR_DEVICE_CLASSES
import nl.teunschriks.mumamobile.car.CarPresence
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.service.DownloadService
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Storage
import nl.teunschriks.mumamobile.util.Util
import okhttp3.OkHttpClient
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * `platform.system` — the shell itself.
 *
 * Implements the `PlatformSystem` typedef of `services/frontend/src/lib/platform/index.js`, plus
 * the two things only a native shell can do: hand the web UI back to the Kotlin app, and open the
 * Kotlin settings screen for the phone-only preferences the web player has no page for yet.
 *
 * | JS contract | here |
 * |---|---|
 * | `isNative` | `isNative()` → `{value: true}` |
 * | `appVersion()` | `appVersion()` → `{version, versionCode, buildType, packageName, androidVersion, device}`, see [appVersion] |
 * | `checkForUpdate()` | `checkForUpdate()` → `{available, currentVersionCode, currentVersionName, currentSeries, latestVersionCode, latestVersionName, latestSeries, url}`, rejects when the hoster cannot be asked; see [checkForUpdate] |
 * | `openUrl({url})` | `openUrl({url})`, an `ACTION_VIEW` to whatever handles it; rejects when nothing does |
 * | `releaseNotes()` | `releaseNotes()` → `{text}`, muma-mobile's own `CHANGELOG.md` |
 * | `serverUrl()` | `serverUrl()` → `{subsonic, mumaApi}` |
 * | `signOut()` | `signOut()` |
 * | `saveCredentials({url, username, password})` | `saveCredentials()` |
 * | `onBack(fn)` | listener on the `back` event, answered with `handledBack({seq})` |
 * | `onDeepLink(fn)` | listener on the `deepLink` event |
 * | `carConnected(fn)` | listener on the `carConnected` event |
 * | `carState()` | `carState()` → `{connected}`, see [carState] |
 * | `setKeepScreenOn({showWhenLocked, turnScreenOn})` | [setKeepScreenOn] |
 * | `getSettings()` | a snapshot of the device-settings tab's fields, see [getSettings] |
 * | `setSetting({key, value})` | [DEVICE_SETTING_WHITELIST], see [setSetting] |
 * | `outputRoute()` | `outputRoute()` → `{name, type}`, see [outputRoute] |
 * | `onOutputRouteChanged(fn)` | listener on the `outputRouteChanged` event, fed by an [OutputRouteMonitor] |
 * | `openOutputPicker()` | `openOutputPicker()`, the system output switcher, see [openOutputPicker] |
 *
 * ### The back protocol
 *
 * Android's back gesture is not browser history, and the WebView cannot be asked whether the UI
 * *wants* it — a modal sheet is not a history entry. So [CapacitorActivity] does this, in order:
 *
 * 1. `webView.canGoBack()` → `goBack()`, and JS is not told. History wins, always.
 * 2. Otherwise it emits `back` with a monotonically increasing `{seq}` and starts a
 *    [CapacitorActivity.BACK_CLAIM_WINDOW_MS] timer.
 * 3. If the web UI closed something it calls `handledBack({seq})` with that same `seq` before the
 *    timer fires, and nothing else happens.
 * 4. If it does not, the activity finishes, which is what a back press at the top of an app does.
 *
 * The sequence number is what keeps a slow claim from swallowing a later press: a `handledBack`
 * for an older `seq` is ignored.
 */
@CapacitorPlugin(name = "MumaSystem")
class MumaSystemPlugin :
    Plugin(),
    KoinComponent {

    private val activeServerProvider: ActiveServerProvider by inject()
    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val carPresence: CarPresence by inject()

    /** Set by [CapacitorActivity] so a claim can cancel the pending finish. */
    var onBackClaimed: ((Long) -> Unit)? = null

    /**
     * Started in [load] rather than lazily on the first `onOutputRouteChanged` subscription: the
     * web UI subscribes from a component's mount, and Capacitor has no hook for "a listener was
     * added", so the only place the registration can be paired with a teardown is the plugin's
     * own lifetime.
     */
    private var outputRoutes: OutputRouteMonitor? = null

    override fun load() {
        instance = this
        outputRoutes = safeContext?.let { context ->
            OutputRouteMonitor(context) { route -> notifyListeners(EVENT_OUTPUT_ROUTE_CHANGED, route.asJs()) }
        }?.also { it.start() }
    }

    override fun handleOnDestroy() {
        if (instance === this) instance = null
        onBackClaimed = null
        outputRoutes?.stop()
        outputRoutes = null
        calls.cancel()
    }

    @PluginMethod
    fun isNative(call: PluginCall) {
        call.resolve(JSObject().put("value", true))
    }

    /**
     * The APK's own `versionName` (e.g. "6.35.1"), for the web UI's once-per-upgrade release
     * notes -- see `mobileReleaseNotes.js`. Deliberately not `WebEnvironment`'s bundle version:
     * that one is a git short hash the frontend build stamps on itself, useful for a crash
     * report but not something a semantic-version comparison or muma-mobile's own
     * `CHANGELOG.md` headings can be matched against. An empty string is what a `PackageManager`
     * that could not find this app's own package answers with -- practically never, but the web
     * side already treats a blank answer as "nothing to compare", the same way it treats a
     * first install with no prior version stored.
     */
    @PluginMethod
    fun appVersion(call: PluginCall) {
        val version = safeContext?.let { Util.getVersionName(it) } ?: ""
        call.resolve(
            JSObject()
                .put("version", version)
                // The rest is what the About page lists and what a bug report is asked for;
                // `BuildConfig` rather than `PackageManager` because it cannot fail to answer.
                .put("versionCode", BuildConfig.VERSION_CODE)
                .put("buildType", BuildConfig.BUILD_TYPE)
                .put("packageName", BuildConfig.APPLICATION_ID)
                .put("androidVersion", "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        )
    }

    /**
     * Asks apk-hoster whether a newer build exists -- the check the legacy Kotlin home screen
     * ran on every start (`util/UpdateChecker.kt`, deleted with that screen) and that nothing
     * ran since, which is how a phone on build 312 heard nothing about 313.
     *
     * A release build asks after its own series; a debug build asks after its own *and* the
     * release series and is told about the newer of the two ([AppUpdate.seriesToAsk]), so a
     * debug phone hears that a release outran it even when nobody pressed `mobile:build-debug`.
     * The answer names the series the newest build came from (`latestSeries`) next to this
     * build's own (`currentSeries`); the web words a cross-series answer differently, since the
     * release APK installs beside the debug one rather than over it.
     *
     * The plugin only fetches and compares; the web decides when to ask (once a day on start,
     * and whenever the About page's button is pressed) and how to tell the listener. A hoster
     * that cannot be reached or answers with an error *rejects* rather than resolving
     * `available: false`: "you are up to date" and "I could not check" are different answers,
     * and the manual button has to show the second one as such. With two series asked, one
     * answer is enough: the check only rejects when neither series could be read.
     */
    @PluginMethod
    fun checkForUpdate(call: PluginCall) {
        val ownSeries = AppUpdate.seriesOf(BuildConfig.DEBUG)
        calls.runCall(call) { answer ->
            val answers = mutableListOf<AppUpdate.Latest>()
            var firstFailure: Throwable? = null
            for (series in AppUpdate.seriesToAsk(BuildConfig.DEBUG)) {
                val url = AppUpdate.versionUrl(BuildConfig.APK_HOST_URL, series)
                try {
                    answers += AppUpdate.fetchLatest(
                        updateClient,
                        url,
                        BuildConfig.VERSION_NAME,
                        series
                    )
                } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                    Timber.w(all, "Could not check for an update at %s", url)
                    if (firstFailure == null) firstFailure = all
                }
            }
            val latest = AppUpdate.newest(answers)
            if (latest == null) {
                withContext(Dispatchers.Main) { answer.reject("update check failed: ${firstFailure?.message}") }
                return@runCall
            }
            val current = BuildConfig.VERSION_CODE
            withContext(Dispatchers.Main) {
                answer.resolve(
                    JSObject()
                        .put("available", AppUpdate.isNewer(latest, current))
                        .put("currentVersionCode", current)
                        .put("currentVersionName", BuildConfig.VERSION_NAME)
                        .put("currentSeries", ownSeries)
                        .put("latestVersionCode", latest.versionCode)
                        .put("latestVersionName", latest.versionName)
                        .put("latestSeries", latest.series)
                        .put("url", AppUpdate.downloadUrl(latest.url))
                )
            }
        }
    }

    /**
     * Opens a url outside the WebView -- the download link of a newer build, which the WebView
     * itself must not navigate to (an APK is not a page). Rejects when no installed app takes
     * `ACTION_VIEW` for it, so the web can say so instead of nothing happening.
     */
    @PluginMethod
    fun openUrl(call: PluginCall) {
        val url = call.getString("url")
        if (url.isNullOrBlank()) {
            call.reject("openUrl needs a url")
            return
        }
        val activity = runningActivity
        if (activity == null) {
            call.reject("no activity to open a url from")
            return
        }
        try {
            activity.startActivity(Intent(Intent.ACTION_VIEW, url.toUri()))
            call.resolve()
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Nothing could open %s", url)
            call.reject("nothing on this device opens that url")
        }
    }

    /**
     * The text of muma-mobile's own `CHANGELOG.md`, for the web UI's once-per-upgrade release
     * notes -- see `mobileReleaseNotes.js`.
     *
     * Read from `assets/CHANGELOG.md` rather than bundled into the frontend itself:
     * `frontend:bundle`'s Docker build context is `services/frontend` alone, so a build-time
     * import reaching into `services/muma-mobile` cannot resolve there even though it resolves
     * fine under a local `vite dev`/`vitest` run against the full checkout. `copyChangelog` in
     * `app/build.gradle` already stages this exact file into the APK's assets -- reading it
     * here needs no new Gradle wiring.
     *
     * An empty string is what a missing asset (no bridge attached, or a checkout where
     * `copyChangelog` never ran) answers with; the web side already treats that the same as "no
     * asset at all".
     */
    @PluginMethod
    fun releaseNotes(call: PluginCall) {
        val text = safeContext?.let {
            try {
                it.assets.open(CHANGELOG_ASSET).bufferedReader().use { reader -> reader.readText() }
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                null
            }
        } ?: ""
        call.resolve(JSObject().put("text", text))
    }

    /**
     * `context`, not `activity`: [appVersion] and [releaseNotes] only need a `PackageManager`/
     * `AssetManager`, and unlike `activity` (see [runningActivity]) `context` throws rather than
     * answers null when the bridge is not attached -- true for a bare-constructed plugin in a
     * test, never in production.
     */
    private val safeContext: Context?
        get() = try {
            context
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            null
        }

    /**
     * `Plugin.getActivity()` reads `bridge.getActivity()` with no null check of its own, so an
     * unattached bridge throws rather than answering null -- true only outside a running app (a
     * bare-constructed plugin in a test), but caught here so every "no activity" reject in this
     * class is reachable at all rather than only ever NPE-ing.
     */
    private val runningActivity: Activity?
        get() = try {
            activity
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            null
        }

    /** One client for the update check; the app's Subsonic client is bound to the server, not the hoster. */
    private val updateClient by lazy { OkHttpClient() }
    private val calls = PluginCallScope("MumaSystem")

    /**
     * The two bases every URL in the web player is built on.
     *
     * `subsonic` is the LMS server the app is logged in to; `mumaApi` is derived from it exactly
     * as `SubsonicAPIClient.mumaBaseUrlFor` does for the native code, so the shell and the Kotlin
     * app can never disagree about which backend they are talking to. Neither is ever an empty
     * string here: a native shell has no origin to fall back on.
     *
     * Read from [ActiveServerProvider.signInServer] rather than the active server: with Offline
     * active (every fresh install) the active url is `http://localhost`, the WebView's own origin,
     * and every request the web player made would have been answered by its own index.html.
     */
    @PluginMethod
    fun serverUrl(call: PluginCall) {
        val urls = serverUrlsOf(activeServerProvider.signInServer().url)
        call.resolve(
            JSObject()
                .put("subsonic", urls.subsonic)
                .put("mumaApi", urls.mumaApi)
        )
    }

    /**
     * What the web login needs, taken from where the native client already keeps it.
     *
     * `username`/`password` are the Subsonic credentials `SubsonicAPIClient` signs every `/rest` endpoint
     * call with — the same pair, not a second auth path: the interceptors hash the password per
     * request, they do not hold a token. `clientId` is the `c=` parameter the server records
     * sessions against. `mumaApiKey` and `mumaUserId` are the muma API's own credentials, and are
     * absent when the user has never signed in there.
     *
     * `password` is blank exactly when the app considers itself logged out, which is the same
     * check `NavigationActivity` makes before showing the welcome screen.
     */
    @PluginMethod
    fun credentials(call: PluginCall) {
        val server = activeServerProvider.getActiveServer()
        val result = JSObject()
            .put("username", server.userName)
            .put("password", server.password)
            .put("clientId", Constants.REST_CLIENT_ID)
            .put("forcePlainTextPassword", server.forcePlainTextPassword)
            .put("serverId", server.id)
        Settings.mumaApiKey.takeIf { it.isNotBlank() }?.let { result.put("mumaApiKey", it) }
        Settings.mumaUserId.takeIf { it > 0 }?.let { result.put("mumaUserId", it) }
        call.resolve(result)
    }

    /**
     * Ends the session started in the Svelte shell, the same way the legacy logout menu does.
     *
     * The queue goes first -- [MediaPlayerManager.clear], never `onDestroy()`: both are root
     * `single`s (see `di/MediaPlayerModule.kt`), application-scoped and started once, and
     * `onDestroy()` tears down the controller and the external-storage monitor for the whole app,
     * not just the session. [ActiveServerProvider.signOut] then clears the password, the muma API
     * key/user id and the encrypted muma tokens, exactly as `NavigationActivity.logOut` does, so
     * there is one definition of "signed out" for both UIs. The username and any downloaded files
     * are left alone.
     */
    @PluginMethod
    fun signOut(call: PluginCall) {
        mediaPlayerManager.clear()
        activeServerProvider.signOut()
        call.resolve()
    }

    /**
     * Persists a username/password pair the Svelte login screen just verified, so downloads,
     * Android Auto and the legacy UI see the same session afterwards. Goes through
     * [ActiveServerProvider.saveCredentials]. `url` is accepted for symmetry with the JS contract
     * but not stored: static mode has exactly one server address (see
     * `StaticServers.STATIC_SERVERS`), so there is nowhere on this side to put a different
     * one.
     */
    @PluginMethod
    fun saveCredentials(call: PluginCall) {
        val username = call.getString("username") ?: ""
        val password = call.getString("password") ?: ""
        activeServerProvider.saveCredentials(username, password)
        call.resolve()
    }

    /** Step 3 of the back protocol. See the class comment. */
    @PluginMethod
    fun handledBack(call: PluginCall) {
        val seq = call.getInt("seq")?.toLong() ?: -1L
        onBackClaimed?.invoke(seq)
        call.resolve()
    }

    /** Emitted by [CapacitorActivity] when the platform back gesture reached the top of the UI. */
    fun emitBack(seq: Long) = notifyListeners(EVENT_BACK, JSObject().put("seq", seq))

    /**
     * A route the router understands, e.g. `album:123`. Built by [CapacitorActivity] from the
     * intent extras the Kotlin app has always used, so the quick-settings tile, the car-mode
     * notification and the launcher shortcut keep working.
     */
    fun emitDeepLink(route: String) = notifyListeners(EVENT_DEEP_LINK, JSObject().put("route", route))

    fun emitCarConnected(connected: Boolean) = notifyListeners(EVENT_CAR_CONNECTED, JSObject().put("connected", connected))

    /**
     * The value [emitCarConnected] would have sent had the web UI been listening from the start.
     *
     * `carConnected` only reaches a listener that subscribed before the event fired, and
     * [nl.teunschriks.mumamobile.activity.CapacitorActivity] starts watching presence in `onCreate`
     * -- before the WebView has necessarily finished loading and registered this plugin's
     * listener. Bootstrap therefore has to ask rather than wait: read [CarPresence.isInCar] once, the
     * same source [nl.teunschriks.mumamobile.activity.CapacitorActivity] emits from, so the answer
     * here and the next event agree.
     */
    @PluginMethod
    fun carState(call: PluginCall) {
        call.resolve(JSObject().put("connected", carPresence.isInCar.value))
    }

    /**
     * Lets the web UI ask for the lock-screen behaviour the legacy car-mode screen gets from
     * `NavigationActivity`'s destination listener -- there is no destination here to key it off,
     * so the web view asks explicitly when its own car screen is on top, and again with both flags
     * false when it closes.
     *
     * Both flags are applied together and default to `false` when absent, so a call that forgets
     * one does not leave the other stuck on from a previous call.
     */
    @PluginMethod
    fun setKeepScreenOn(call: PluginCall) {
        val running = runningActivity
        if (running == null) {
            call.reject("no activity")
            return
        }
        val showWhenLocked = call.getBoolean("showWhenLocked") ?: false
        val turnScreenOn = call.getBoolean("turnScreenOn") ?: false
        running.runOnUiThread {
            running.setShowWhenLocked(showWhenLocked)
            running.setTurnScreenOn(turnScreenOn)
        }
        call.resolve()
    }

    /**
     * Tells the shell which language the web `LanguageSetting` just picked
     * (`services/frontend/src/lib/settings/LanguageSetting.svelte`), so the native chrome --
     * permission dialogs, share sheets, anything `CapacitorActivity.attachBaseContext` wraps with
     * [nl.teunschriks.mumamobile.util.LocaleHelper] -- follows the same language as the web UI's
     * own text, not whatever locale the device happened to boot with.
     *
     * Recreating the activity is the only way that context wrapper runs again; the WebView reloads
     * as a result, which is expected for a rare, deliberate settings change rather than something
     * this is ever called on every boot.
     */
    @PluginMethod
    fun setAppLocale(call: PluginCall) {
        Settings.overrideLanguage = call.getString("locale") ?: ""
        call.resolve()
        activity?.runOnUiThread { activity?.recreate() }
    }

    /**
     * The "Apparaat" settings tab's whole state in one call: every field
     * [DEVICE_SETTING_WHITELIST] can write, plus a few read-only ones the tab only ever shows --
     * the cache location and how many car-mode devices are paired.
     *
     * `carModeFullScreenGranted` is left out entirely below Android 14 and where
     * [NotificationManager] cannot answer, exactly as the legacy row hides itself in that case --
     * the web UI reads a missing key as "not applicable" rather than as `false`.
     */
    @PluginMethod
    fun getSettings(call: PluginCall) {
        val result = JSObject()
            .put("wifiOnly", Settings.isWifiRequiredForDownload)
            .put("parallelDownloads", Settings.parallelDownloads)
            .put("cacheSizeMB", sentinelToUnlimited(Settings.cacheSizeMB))
            .put("cacheLocationUri", Settings.cacheLocationUri)
            .put("customCacheLocation", Settings.customCacheLocation)
            .put("maxBitrateMobile", Settings.maxBitRateMobile)
            .put("maxBitrateWifi", Settings.maxBitRateWifi)
            .put("maxBitratePinning", Settings.maxBitRatePinning)
            .put("preloadCount", sentinelToUnlimited(Settings.preloadCount))
            .put("resumeOnHeadphonesPlug", Settings.resumePlayOnHeadphonePlug)
            .put("resumeOnBluetoothDevice", Settings.resumeOnBluetoothDevice)
            .put("pauseOnBluetoothDevice", Settings.pauseOnBluetoothDevice)
            .put("hardwareOffload", Settings.useHwOffload)
            .put("carModeManual", Settings.carModeManual)
            .put("carModeDevices", JSArray(Settings.carModeDevices.toList()))
            .put("networkTimeout", Settings.networkTimeout)
            .put("autoSwitchOffline", Settings.autoSwitchOffline)
            .put("directoryCacheTime", Settings.directoryCacheTime)
            .put("hideMedia", Settings.hideMedia)
            .put("mediaDeviceExport", Settings.mediaDeviceExportEnabled)
            .put("scrobbleEnabled", Settings.scrobbleEnabled)
        // Read-only: login fills both (ActiveServerProvider.setMumaSettings), nothing here lets a
        // user edit them. mumaApiKeySet rather than the raw key, same reason updatePreferenceSummaries
        // masks it on the legacy screen instead of showing it back.
        Settings.mumaUserId.takeIf { it > 0 }?.let { result.put("mumaUserId", it) }
        result.put("mumaApiKeySet", Settings.mumaApiKey.isNotBlank())
        fullScreenIntentGranted()?.let { result.put("carModeFullScreenGranted", it) }
        call.resolve(result)
    }

    /**
     * Writes one field of the device-settings tab, through [writeDeviceSetting] and
     * [DEVICE_SETTING_WHITELIST]. An unknown key or a value of the wrong type rejects the call
     * rather than writing a preference nothing validated -- the same reason `credentials()` above
     * never trusts the bridge either.
     *
     * `value` is read as the type the whitelist declares for `key`, because `PluginCall` has no
     * "give me whatever this is" accessor; a key not in the whitelist is rejected before either
     * accessor runs, so there is nothing to read a wrong-typed value from in the first place.
     */
    @PluginMethod
    fun setSetting(call: PluginCall) {
        val key = call.getString("key")
        if (key.isNullOrBlank()) {
            call.reject("missing key")
            return
        }
        val spec = DEVICE_SETTING_WHITELIST[key]
        if (spec == null) {
            call.reject("unknown setting: $key")
            return
        }
        val value: Any? = when (spec.type) {
            DeviceSettingType.BOOLEAN -> call.getBoolean("value")
            DeviceSettingType.INT -> call.getInt("value")
            DeviceSettingType.STRING_SET -> call.getArray("value")?.let { jsArrayToStringSet(it) }
        }
        when (writeDeviceSetting(key, value)) {
            DeviceSettingWriteResult.OK -> call.resolve()
            DeviceSettingWriteResult.INVALID_VALUE -> call.reject("invalid value for $key")
            // Already handled above; the whitelist cannot change between the two lookups.
            DeviceSettingWriteResult.UNKNOWN_KEY -> call.reject("unknown setting: $key")
        }
    }

    /**
     * The paired Bluetooth devices, for the Apparaat tab's car-mode picker.
     *
     * `permissionGranted` is answered rather than an empty list left to speak for itself: a phone
     * with the permission denied and a phone with nothing paired both have zero devices, and only
     * one of those is something a "grant access" row should react to. Same permission check and
     * same "which class looks like a car" guess as the legacy picker
     * (`SettingsFragment.setupCarModeDevices`) -- see [CAR_DEVICE_CLASSES].
     */
    @PluginMethod
    fun listBondedDevices(call: PluginCall) {
        val activity = activity ?: run {
            call.resolve(JSObject().put("permissionGranted", false).put("devices", JSArray()))
            return
        }
        val granted = ActivityCompat.checkSelfPermission(activity, Manifest.permission.BLUETOOTH_CONNECT) ==
            PackageManager.PERMISSION_GRANTED
        val result = JSObject().put("permissionGranted", granted)
        if (!granted) {
            call.resolve(result.put("devices", JSArray()))
            return
        }
        val adapter = activity.getSystemService(BluetoothManager::class.java)?.adapter
        val devices = adapter?.bondedDevices.orEmpty().map {
            JSObject()
                .put("address", it.address)
                .put("name", it.name ?: it.address)
                .put("isCarClass", it.bluetoothClass?.deviceClass in CAR_DEVICE_CLASSES)
        }
        call.resolve(result.put("devices", JSArray(devices)))
    }

    /**
     * Fires the system settings screen where the user can grant the "use full screen intent"
     * permission car mode raises the screen with. Fire-and-forget: there is no result to wait
     * for, only `getSettings`'s `carModeFullScreenGranted` on the next read.
     */
    @PluginMethod
    fun requestCarModeFullScreenPermission(call: PluginCall) {
        // Same guard as fullScreenIntentGranted()/the legacy row's own visibility check: below
        // Android 14 the permission does not exist, and the action below is API 34.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            call.resolve()
            return
        }
        val activity = activity ?: run {
            call.reject("no activity")
            return
        }
        activity.runOnUiThread {
            activity.startActivity(
                Intent(android.provider.Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
                    .setData("package:${activity.packageName}".toUri())
            )
        }
        call.resolve()
    }

    /**
     * Which output media plays through right now, for the label on the player screen:
     * `{name, type}`, with `type` one of [OutputRouteType]'s wire words. The route is computed in
     * [currentOutputRoute] and the choice explained at [outputRouteOf] -- in short, the
     * *available* outputs are listed and the one Android would pick is named, which for a phone
     * is the same thing. Never rejects: a phone with no listed devices is answered with the
     * speaker. The one answer that is not a route is an empty object, for a plugin with no
     * bridge attached yet; the web side reads that as "nothing to show", the same as a browser.
     */
    @PluginMethod
    fun outputRoute(call: PluginCall) {
        val context = safeContext
        if (context == null) {
            call.resolve(JSObject())
            return
        }
        call.resolve(currentOutputRoute(context).asJs())
    }

    /**
     * Opens the system output switcher -- the same panel Spotify's and YouTube Music's own
     * output buttons open -- or, on a build without one, the Bluetooth settings screen; see
     * [outputPickerIntents]. Resolves as soon as one of them started, since there is no result
     * to wait for: the switch itself arrives as an `outputRouteChanged` event. Rejects only when
     * neither intent resolves, so the web can say so instead of nothing happening. Started
     * from this thread rather than `runOnUiThread` on purpose: `ActivityNotFoundException` has
     * to be caught *here* to try the fallback, and a post to the main looper would throw it
     * there instead.
     */
    @PluginMethod
    fun openOutputPicker(call: PluginCall) {
        val activity = runningActivity
        if (activity == null) {
            call.reject("no activity to open the output picker from")
            return
        }
        val started = startFirstResolvable(outputPickerIntents(activity.packageName)) { activity.startActivity(it) }
        if (started) call.resolve() else call.reject("nothing on this device opens an output picker")
    }

    /**
     * Opens the system's directory picker (`ACTION_OPEN_DOCUMENT_TREE`) for a custom cache
     * location. The result comes back through [onCacheLocationPicked]; this only has to start the
     * intent.
     */
    @PluginMethod
    fun pickCacheLocation(call: PluginCall) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            .addFlags(CACHE_LOCATION_RW_FLAG)
            .addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        // No SDK_INT guard here: minSdk is 33, well above the O (26) SelectCacheActivityContract
        // still checks for on the legacy path.
        if (Settings.cacheLocationUri.isNotEmpty()) {
            intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, Settings.cacheLocationUri.toUri())
        }
        startActivityForResult(call, intent, "onCacheLocationPicked")
    }

    /**
     * The other half of [pickCacheLocation]: takes a persistable permission on the chosen tree,
     * writes it through exactly what `SettingsFragment.setCacheLocation` does (clearing the
     * download queue and resetting [Storage] against the new root), and resolves with the path the
     * device-settings tab already shows via `cacheLocationUri`. Resolves with no `uri` -- not a
     * rejection -- when the user backed out of the picker; a cancelled pick is not a failure.
     */
    // detekt cannot see the call: Capacitor invokes this by the string name passed to
    // startActivityForResult above, not a direct Kotlin reference.
    @Suppress("UnusedPrivateMember")
    @ActivityCallback
    private fun onCacheLocationPicked(call: PluginCall?, result: ActivityResult) {
        if (call == null) return
        val uri = if (result.resultCode == Activity.RESULT_OK) result.data?.data else null
        if (uri == null) {
            call.resolve(JSObject())
            return
        }
        context?.contentResolver?.takePersistableUriPermission(uri, CACHE_LOCATION_RW_FLAG)
        Settings.cacheLocationUri = uri.toString()
        Settings.customCacheLocation = true
        DownloadService.clearDownloads()
        Storage.reset()
        Storage.checkForErrorsWithCustomRoot()
        call.resolve(JSObject().put("uri", uri.toString()).put("path", uri.path ?: ""))
    }

    /**
     * Turns a custom cache location back off, the same as unchecking the legacy screen's
     * "custom_cache_location" box with nothing picked yet: back to the default location, download
     * queue cleared, [Storage] reset against it.
     */
    @PluginMethod
    fun clearCustomCacheLocation(call: PluginCall) {
        Settings.customCacheLocation = false
        Settings.cacheLocationUri = ""
        DownloadService.clearDownloads()
        Storage.reset()
        Storage.checkForErrorsWithCustomRoot()
        call.resolve()
    }

    /**
     * Whether Android has granted the "use full screen intent" permission the car-mode
     * notification raises the screen with, or `null` where the question does not apply: below
     * Android 14 every app has it implicitly. Mirrors `SettingsFragment.setupCarModeFullScreen`,
     * which hides its row on exactly the same condition instead of answering `null`.
     *
     * Catches everything rather than letting `getSettings` fail over one optional field: a plugin
     * with no bridge attached yet -- true for a moment during every cold start -- has no [context]
     * to ask, and answering "not applicable" is the honest read of that, not an error.
     */
    private fun fullScreenIntentGranted(): Boolean? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.UPSIDE_DOWN_CAKE) return null
        return try {
            context?.getSystemService(NotificationManager::class.java)?.canUseFullScreenIntent()
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Could not read the full-screen-intent permission")
            null
        }
    }

    companion object {
        const val EVENT_BACK = "back"
        const val EVENT_DEEP_LINK = "deepLink"
        const val EVENT_CAR_CONNECTED = "carConnected"
        const val EVENT_OUTPUT_ROUTE_CHANGED = "outputRouteChanged"

        /** Same flags `SettingsFragment`'s `RW_FLAG` grants the legacy cache-location picker. */
        const val CACHE_LOCATION_RW_FLAG = Intent.FLAG_GRANT_READ_URI_PERMISSION or
            Intent.FLAG_GRANT_WRITE_URI_PERMISSION

        /** Staged into the APK's assets by `copyChangelog` in `app/build.gradle`. See [releaseNotes]. */
        private const val CHANGELOG_ASSET = "CHANGELOG.md"

        /**
         * The bridge builds plugins, so the activity cannot construct one. It looks the live
         * instance up here instead; null until the WebView has loaded.
         */
        @Volatile
        var instance: MumaSystemPlugin? = null
            internal set

        /** Never throws: a shell event must not be able to take the activity down with it. */
        fun emit(what: String, block: (MumaSystemPlugin) -> Unit) {
            val plugin = instance ?: return
            try {
                block(plugin)
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                Timber.w(all, "Failed to emit %s to the web UI", what)
            }
        }
    }
}

// The two pure helpers below live outside the class on purpose: every `platform.system` member
// has to be a method of the plugin, and detekt's per-class function ceiling (`TooManyFunctions`,
// 30) is what the plugin would otherwise run into first.

/** `-1` is the on-disk sentinel for "no limit"; both preferences answer [Int.MAX_VALUE] for it. */
private fun sentinelToUnlimited(value: Int): Int = if (value == Int.MAX_VALUE) -1 else value

/**
 * `PluginCall.getArray` hands back a `JSArray` (a `org.json.JSONArray`), not a `Set<String>`;
 * this is the one conversion [MumaSystemPlugin.setSetting] needs for
 * [DeviceSettingType.STRING_SET]. Anything that is not a string is dropped rather than failing
 * the whole call -- the bridge serialises a JS array of strings faithfully, so a non-string entry
 * would mean a caller bug, not a user mistake worth rejecting the write for.
 */
private fun jsArrayToStringSet(array: JSArray): Set<String> = buildSet {
    for (i in 0 until array.length()) (array.opt(i) as? String)?.let { add(it) }
}
