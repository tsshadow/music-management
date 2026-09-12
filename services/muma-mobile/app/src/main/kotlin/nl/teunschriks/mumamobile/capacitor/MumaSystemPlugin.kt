/*
 * MumaSystemPlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.Intent
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import nl.teunschriks.mumamobile.activity.NavigationActivity
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.UiVariant
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
 * | `serverUrl()` | `serverUrl()` → `{subsonic, mumaApi}` |
 * | `onBack(fn)` | listener on the `back` event, answered with `handledBack({seq})` |
 * | `onDeepLink(fn)` | listener on the `deepLink` event |
 * | `carConnected(fn)` | listener on the `carConnected` event |
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

    /** Set by [CapacitorActivity] so a claim can cancel the pending finish. */
    var onBackClaimed: ((Long) -> Unit)? = null

    override fun load() {
        instance = this
    }

    override fun handleOnDestroy() {
        if (instance === this) instance = null
        onBackClaimed = null
    }

    @PluginMethod
    fun isNative(call: PluginCall) {
        call.resolve(JSObject().put("value", true))
    }

    /**
     * The two bases every URL in the web player is built on.
     *
     * `subsonic` is the LMS server the app is logged in to; `mumaApi` is derived from it exactly
     * as `SubsonicAPIClient.mumaBaseUrlFor` does for the native code, so the shell and the Kotlin
     * app can never disagree about which backend they are talking to. Neither is ever an empty
     * string here: a native shell has no origin to fall back on.
     */
    @PluginMethod
    fun serverUrl(call: PluginCall) {
        val urls = serverUrlsOf(activeServerProvider.getActiveServer().url)
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
     * Puts the setting back on the Kotlin app and restarts into it.
     *
     * The task is cleared rather than the activity finished: the web UI is the task's root, and
     * leaving it on the stack would let one back press return to the interface the user just
     * left. No launcher component is disabled on the way out -- the aliases point at the
     * trampoline, which reads the setting -- because disabling one takes this very task down with
     * it. See `activity/LauncherActivity.kt`.
     */
    @PluginMethod
    fun switchToLegacyUi(call: PluginCall) {
        val activity = activity ?: run {
            call.reject("no activity")
            return
        }
        Settings.webUiEnabled = false
        call.resolve()
        activity.runOnUiThread {
            activity.startActivity(
                UiVariant.launchIntent(activity)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            )
            activity.finish()
        }
    }

    /**
     * Opens the Kotlin settings screen on top of the web UI.
     *
     * Phase 1 leaves downloads, cache location, the car and the equalizer configured there; the
     * web player has no page for them yet, and a second, half-complete settings screen would be
     * worse than a visible seam.
     */
    @PluginMethod
    fun openLegacySettings(call: PluginCall) {
        val activity = activity ?: run {
            call.reject("no activity")
            return
        }
        activity.runOnUiThread {
            activity.startActivity(
                Intent(activity, NavigationActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra(EXTRA_OPEN_SETTINGS, true)
            )
        }
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

    companion object {
        const val EVENT_BACK = "back"
        const val EVENT_DEEP_LINK = "deepLink"
        const val EVENT_CAR_CONNECTED = "carConnected"

        /** Tells [NavigationActivity] to open its settings screen; see [openLegacySettings]. */
        const val EXTRA_OPEN_SETTINGS = "nl.teunschriks.mumamobile.OPEN_SETTINGS"

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
