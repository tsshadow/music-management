/*
 * CapacitorActivity.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.activity

import android.app.SearchManager
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebView
import androidx.activity.OnBackPressedCallback
import androidx.lifecycle.lifecycleScope
import com.getcapacitor.BridgeActivity
import com.getcapacitor.WebViewListener
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.capacitor.MumaDiagnosticsPlugin
import nl.teunschriks.mumamobile.capacitor.MumaPlayerPlugin
import nl.teunschriks.mumamobile.capacitor.MumaSpeechPlugin
import nl.teunschriks.mumamobile.capacitor.MumaStoragePlugin
import nl.teunschriks.mumamobile.capacitor.MumaSystemPlugin
import nl.teunschriks.mumamobile.capacitor.WindowMode
import nl.teunschriks.mumamobile.car.CarConnectionWatcher
import nl.teunschriks.mumamobile.car.CarModeIntent
import nl.teunschriks.mumamobile.car.CarModeNotifier
import nl.teunschriks.mumamobile.car.CarModeSession
import nl.teunschriks.mumamobile.car.CarPresence
import nl.teunschriks.mumamobile.diagnostics.CrashReportManager
import nl.teunschriks.mumamobile.service.BookmarkMigration
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.LocaleHelper
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.voice.VoiceTileService
import org.koin.android.ext.android.inject
import timber.log.Timber

/**
 * The app's interface: the Svelte web player in a `WebView`, over the Kotlin services.
 *
 * It is the only UI in the APK. The Kotlin screens and their `NavigationActivity` were deleted
 * (MR !783); every launcher alias opens `LauncherActivity`, a trampoline that starts this
 * activity (see `AppIconVariant` and `LauncherActivity`). Everything below the screens is Kotlin:
 * `PlaybackService`, the media session, Android Auto, the notification, `DownloadService`, Room
 * and the Koin graph. This activity owns the parts that are the *app's* lifecycle rather than a
 * screen's, which it took over from `NavigationActivity`:
 *
 * - `Util.applyTheme` and the locale/scale [attachBaseContext] wrapping, so a WebView launched
 *   from a shortcut is configured the same way every other screen is;
 * - `volumeControlStream`, so the hardware keys reach the music stream and not the ringer;
 * - the notification permission, asked once;
 * - `lifecycleSupport.onCreate()` in [onResume], which is what starts the player's event
 *   receivers -- it is deliberately *not* in `onCreate`, as it was not in `NavigationActivity`;
 * - `CrashReportManager.maybeHandlePendingReport`, so a pending crash report is offered;
 * - the car-presence loop, which here emits `carConnected` to the web UI instead of navigating;
 * - the window mode (`full`, `split`, `pip`), emitted as `windowModeChanged` so the web UI can
 *   show its compact player (`docs/designs/miniplayer/`).
 *
 * Deep links arrive the way they always have -- as intent extras and actions -- and are
 * translated into the route strings the web router understands, so the quick-settings tile, the
 * car-mode notification, the launcher shortcut and a search intent all still land somewhere.
 *
 * ### Where the web side plugs in
 *
 * - The bundle is read from `assets/public/`, which the `prepareWebBundle` Gradle task fills from
 *   `services/frontend/dist`. It is gitignored; a build without it ships a page that says so.
 * - `assets/capacitor.config.json` is the runtime config. Its paths (`webDir`, `android.path`)
 *   are written relative to `services/frontend`, so the copy the web module keeps for
 *   `@capacitor/cli` is the same file. `plugins.CapacitorHttp.enabled` is true -- that is what
 *   lets the web player reach LMS, which sends no CORS headers at all, and the muma API, whose
 *   allowlist is dev-only.
 * - `server.androidScheme` is **`http`**, which makes the origin `http://localhost`. With the
 *   `https` scheme it used to default to, every cover from a plain-http server on the LAN was
 *   mixed content and Chromium refused it -- "This request has been blocked; the content must be
 *   served over HTTPS", once per image, and the whole UI rendered without artwork. `CapacitorHttp`
 *   hid it for `fetch`, because those requests leave through Kotlin, but an `<img src>` never
 *   touches the plugin. `android.allowMixedContent` is the documented answer and it does not work:
 *   measured on the emulator, the config was parsed (`isMixedContentAllowed` true) and the WebView
 *   was at `MIXED_CONTENT_ALWAYS_ALLOW`, and Chromium blocked the images anyway, before and after
 *   a reload. The origin's own scheme is the only lever left. `http://localhost` is still a
 *   trustworthy origin to Chromium, so nothing that needs a secure context is given up, and an
 *   https server keeps working -- https subresources on an http page were never the blocked
 *   direction.
 * - The system bars are the web page's, not the theme's. With targetSdk 35 Android draws them
 *   transparent and ignores `statusBarColor`/`navigationBarColor`; Capacitor's `SystemBars`
 *   plugin then decides whether the WebView sits behind them. It only does so when the page's
 *   viewport meta says `viewport-fit=cover` (and the WebView is 140+); otherwise it pads the
 *   WebView by the insets and the bars show the WebView's own background, which on this phone
 *   was a grey (#303030) nothing in the app had chosen. `services/frontend/index.html` carries
 *   the meta, `backgroundColor` here is the colour of that padding on an older WebView and of
 *   the first frame before the page paints, and `plugins.SystemBars.style` pins light bar icons
 *   regardless of the phone's theme -- the UI is dark on every phone.
 */
class CapacitorActivity : BridgeActivity() {

    private val lifecycleSupport: MediaPlayerLifecycleSupport by inject()
    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val carConnectionWatcher: CarConnectionWatcher by inject()
    private val carPresence: CarPresence by inject()
    private val carModeSession: CarModeSession by inject()
    private val carModeNotifier: CarModeNotifier by inject()

    private val main = Handler(Looper.getMainLooper())
    private var backSequence = 0L
    private var pendingBack: Runnable? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        // Same guard NavigationActivity opens with: an activity can be the process's first, and
        // every `by inject()` below resolves lazily, so a missing container would only surface at
        // the first use rather than here.
        if (UApp.instance != null && !UApp.instance!!.initiated) {
            Timber.d("Starting Koin")
            UApp.instance!!.startKoin()
        }

        // Registered before super.onCreate: the bridge instantiates its plugins there, and one
        // registered after it is simply not in the WebView.
        registerPlugin(MumaPlayerPlugin::class.java)
        registerPlugin(MumaSystemPlugin::class.java)
        registerPlugin(MumaStoragePlugin::class.java)
        registerPlugin(MumaDiagnosticsPlugin::class.java)
        registerPlugin(MumaSpeechPlugin::class.java)

        CrashReportManager.maybeHandlePendingReport(this)
        Util.applyTheme(this)

        super.onCreate(savedInstanceState)

        bridge.addWebViewListener(RendererGoneRestart())
        carConnectionWatcher.start()
        volumeControlStream = AudioManager.STREAM_MUSIC
        Util.ensurePermissionToPostNotification(this)

        installBackHandling()
        watchCarPresence()
        migrateBookmarksOnce()
        deliver(intent)
    }

    /**
     * Android reclaims the WebView's renderer process of a backgrounded app under memory pressure
     * (`didCrash() == false`) and tells the app about it the moment the WebView is shown again.
     * Nobody handled that: Capacitor's `BridgeWebViewClient` asks its listeners and there were
     * none, so the default applied -- the whole app process is killed on the spot. Reopening the
     * app after a while then showed a black WebView for a beat and the app was gone, or the
     * launcher trampoline brought it straight back with nothing in it.
     *
     * Recreating the activity is the documented answer: a new WebView, a new renderer, and the
     * web side boots from the services as after any other WebView loss (`bootstrapShell` reads
     * the session and the queue back from the native side, so playback is not touched). `true`
     * tells the WebView the loss is handled, which is what keeps the process alive to do it.
     */
    private inner class RendererGoneRestart : WebViewListener() {
        override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
            Timber.w("The WebView renderer is gone (crashed=%s); recreating the activity", detail?.didCrash())
            main.post { if (!isFinishing && !isDestroyed) recreate() }
            return true
        }
    }

    override fun onResume() {
        super.onResume()
        // Lifecycle support's constructor registers some event receivers so it should be created
        // early. Same placement as NavigationActivity: onResume, not onCreate.
        lifecycleSupport.onCreate()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        deliver(intent)
    }

    /**
     * Split screen starts, ends or moves. The manifest's `configChanges` keep the activity (and
     * the music, and the web state) alive through it; the web UI only needs to know the mode.
     */
    override fun onMultiWindowModeChanged(isInMultiWindowMode: Boolean, newConfig: Configuration) {
        super.onMultiWindowModeChanged(isInMultiWindowMode, newConfig)
        emitWindowMode()
    }

    /** The floating window opens or closes. Same signal as split screen, with `pip` first. */
    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        emitWindowMode()
    }

    private fun emitWindowMode() {
        val mode = WindowMode.of(isInPictureInPictureMode, isInMultiWindowMode)
        MumaSystemPlugin.emit("windowModeChanged") { it.emitWindowMode(mode) }
    }

    override fun onDestroy() {
        pendingBack?.let(main::removeCallbacks)
        pendingBack = null
        super.onDestroy()
    }

    /**
     * Apply the customized language settings if needed, so the shell's own chrome (permission
     * dialogs, share sheets) is in the language the user picked, not only the WebView's text.
     */
    override fun attachBaseContext(newBase: Context?) {
        val locale = Settings.overrideLanguage
        val localizedContext: Context? = if (locale.isNotEmpty()) {
            LocaleHelper.wrap(newBase, locale)
        } else {
            newBase
        }
        super.attachBaseContext(localizedContext)
    }

    // ------------------------------------------------------------------- back

    /**
     * The back protocol, in full. See [MumaSystemPlugin] for the JS side.
     *
     * 1. The `WebView` has history → go back in it, and do not tell JS. History always wins;
     *    anything else would make the hardware gesture and the on-screen back button disagree.
     * 2. No history → emit `back` with a fresh sequence number and wait [BACK_CLAIM_WINDOW_MS].
     * 3. `MumaSystem.handledBack({seq})` with that sequence number cancels the wait. The web UI
     *    calls it when the press closed a sheet, a dialog or an overlay -- none of which are
     *    history entries, which is precisely why the WebView cannot be asked.
     * 4. The wait expires → `finish()`, which is what back at the root of an app does.
     *
     * The window is short enough not to feel like a stuck button and long enough for a message
     * to cross the bridge twice. A press while a claim is outstanding supersedes it: the older
     * sequence number is no longer the current one, so a late claim is ignored.
     */
    private fun installBackHandling() {
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() = onBack()
            }
        )
        // The bridge builds its plugins during super.onCreate, so the instance is there by now;
        // onBack re-attaches anyway, for the case where the WebView was rebuilt underneath us.
        MumaSystemPlugin.instance?.onBackClaimed = ::onBackClaimed
    }

    private fun onBack() {
        val webView = bridge?.webView
        if (webView != null && webView.canGoBack()) {
            webView.goBack()
            return
        }

        val plugin = MumaSystemPlugin.instance
        if (plugin == null) {
            finish()
            return
        }
        plugin.onBackClaimed = ::onBackClaimed

        pendingBack?.let(main::removeCallbacks)
        backSequence += 1
        val seq = backSequence
        val finisher = Runnable {
            if (backSequence == seq) {
                Timber.d("Back was not claimed by the web UI, finishing")
                finish()
            }
        }
        pendingBack = finisher
        main.postDelayed(finisher, BACK_CLAIM_WINDOW_MS)
        plugin.emitBack(seq)
    }

    private fun onBackClaimed(seq: Long) {
        if (seq != backSequence) return
        pendingBack?.let(main::removeCallbacks)
        pendingBack = null
    }

    // -------------------------------------------------------------- bookmarks

    /**
     * One-time push of this account's Subsonic bookmarks into the web's `setResume` account
     * setting -- see [BookmarkMigration]. The shell's bootstrap is where this runs, once: the
     * Kotlin UI has no equivalent moment (there is no single "app started" screen there, only
     * whichever fragment the user lands on), and the shell is the only surface this design adds
     * anything to. Both network calls block, so this is off the main thread; nothing in the UI
     * waits on it.
     */
    private fun migrateBookmarksOnce() {
        lifecycleScope.launch(Dispatchers.IO) {
            BookmarkMigration.runOnce()
        }
    }

    // -------------------------------------------------------------------- car

    /**
     * The screen is offered, never forced -- same rule as [NavigationActivity]. The difference is
     * what "offer" means here: the web UI decides whether to show its car screen, so presence is
     * handed to it as an event and the notification keeps doing the rest.
     */
    private fun watchCarPresence() {
        lifecycleScope.launch {
            carPresence.isInCar.collectLatest { inCar ->
                MumaSystemPlugin.emit("carConnected") { it.emitCarConnected(inCar) }
                when (carModeSession.onPresenceChanged(inCar) { mediaPlayerManager.isPlaying }) {
                    CarModeIntent.Offer -> carModeNotifier.offer(carModeSession.shouldRaise)
                    CarModeIntent.Close -> carModeNotifier.cancel()
                    CarModeIntent.Nothing -> Unit
                }
            }
        }
    }

    // ------------------------------------------------------------- deep links

    /**
     * Translates the intents the app has always used into routes the web router understands.
     *
     * The extras are the existing cross-process contract -- they are in `PendingIntent`s the
     * system is already holding -- so they are read, not redefined. A route the web does not know
     * is its problem to ignore; sending nothing at all would mean a tap that does nothing.
     */
    private fun deliver(intent: Intent?) {
        val route = routeFor(intent) ?: return
        MumaSystemPlugin.emit("deepLink") { it.emitDeepLink(route) }
    }

    private fun routeFor(intent: Intent?): String? {
        if (intent == null) return null
        if (intent.getBooleanExtra(CarModeNotifier.EXTRA_OPEN_CAR_MODE, false)) return ROUTE_CAR
        if (intent.getBooleanExtra(VoiceTileService.EXTRA_OPEN_VOICE, false)) return ROUTE_VOICE
        if (intent.getBooleanExtra(Constants.INTENT_SHOW_PLAYER, false)) return ROUTE_PLAYER
        return when (intent.action) {
            Constants.INTENT_PLAY_RANDOM_SONGS -> ROUTE_RANDOM
            Intent.ACTION_SEARCH,
            MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH ->
                intent.getStringExtra(SearchManager.QUERY)?.let { "search:$it" }
            else -> null
        }
    }

    companion object {
        /**
         * How long the web UI has to say it used the back press. Two bridge hops and a render;
         * long enough that a busy frame does not lose it, short enough that a press the UI does
         * not want still closes the app without feeling stuck.
         */
        const val BACK_CLAIM_WINDOW_MS = 350L

        const val ROUTE_CAR = "car"
        const val ROUTE_VOICE = "voice"
        const val ROUTE_PLAYER = "player"
        const val ROUTE_RANDOM = "random"
    }
}
