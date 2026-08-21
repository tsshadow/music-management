/*
 * NavigationActivity.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.activity

import android.app.SearchManager
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.content.res.Resources
import android.media.AudioManager
import android.os.Bundle
import android.provider.MediaStore
import android.provider.SearchRecentSuggestions
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuInflater
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.widget.SearchView
import androidx.appcompat.widget.Toolbar
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import androidx.annotation.StringRes
import androidx.core.view.MenuProvider
import androidx.fragment.app.FragmentContainerView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.Player.STATE_BUFFERING
import androidx.media3.common.Player.STATE_READY
import androidx.navigation.NavController
import androidx.navigation.findNavController
import androidx.navigation.fragment.NavHostFragment
import androidx.navigation.fragment.findNavController
import androidx.navigation.ui.AppBarConfiguration
import androidx.navigation.ui.navigateUp
import androidx.navigation.ui.onNavDestinationSelected
import androidx.navigation.ui.setupActionBarWithNavController
import androidx.navigation.ui.setupWithNavController
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import io.reactivex.rxjava3.disposables.CompositeDisposable
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.koin.android.ext.android.inject
import org.koin.androidx.scope.ScopeActivity
import org.koin.androidx.viewmodel.ext.android.viewModel
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.muma.GoogleAuthRequest
import nl.teunschriks.mumamobile.api.muma.MumaAPIClient
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.ServerSetting
import nl.teunschriks.mumamobile.diagnostics.CrashReportManager
import nl.teunschriks.mumamobile.management.ManagementRepository
import nl.teunschriks.mumamobile.model.ServerSettingsModel
import nl.teunschriks.mumamobile.provider.SearchSuggestionProvider
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.LocaleHelper
import nl.teunschriks.mumamobile.util.SecureSettings
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.ShortcutUtil
import nl.teunschriks.mumamobile.util.Storage
import nl.teunschriks.mumamobile.util.UiScaleHelper
import nl.teunschriks.mumamobile.util.UncaughtExceptionHandler
import nl.teunschriks.mumamobile.util.UpdateChecker
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.themeColor
import timber.log.Timber

/**
 * The main (and only) Activity of Ultrasonic which loads all other screens as Fragments.
 * Because this is the only Activity we have to manage the apps lifecycle through this activity
 * onCreate/onResume/onDestroy methods...
 */
@Suppress("TooManyFunctions")
class NavigationActivity : ScopeActivity() {
    private var setsToggleItem: MenuItem? = null
    private var voiceMenuItem: MenuItem? = null

    private var nowPlayingView: FragmentContainerView? = null
    private var nowPlayingHidden = false
    private var bottomNavigationView: BottomNavigationView? = null
    private var host: NavHostFragment? = null
    var setsToggle: MaterialSwitch? = null

    // We store the last search string in this variable.
    // Seems a bit like a hack, is there a better way?
    var searchQuery: String? = null

    private lateinit var appBarConfiguration: AppBarConfiguration

    private var rxBusSubscription: CompositeDisposable = CompositeDisposable()

    private val serverSettingsModel: ServerSettingsModel by viewModel()
    private val lifecycleSupport: MediaPlayerLifecycleSupport by inject()
    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val activeServerProvider: ActiveServerProvider by inject()
    private val subsonicAPIClient: SubsonicAPIClient by inject()
    private val managementRepository: ManagementRepository by inject()

    private var currentFragmentId: Int = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        Timber.d("onCreate called")

        // First check if Koin has been started
        if (UApp.instance != null && !UApp.instance!!.initiated) {
            Timber.d("Starting Koin")
            UApp.instance!!.startKoin()
        } else {
            Timber.d("No need to start Koin")
        }

        setUncaughtExceptionHandler()
        CrashReportManager.maybeHandlePendingReport(this)
        Util.applyTheme(this)

        // Ensure servers are configured early if none exist
        serverSettingsModel.getServerList()

        checkMumaLogin()

        if (BuildConfig.DEBUG && intent.hasExtra("FORCE_LOGIN")) {
            Timber.d("FORCE_LOGIN intent extra found, forcing default server")
            serverSettingsModel.forceDefaultServer()
        }

        super.onCreate(savedInstanceState)

        volumeControlStream = AudioManager.STREAM_MUSIC
        setContentView(R.layout.navigation_activity)
        nowPlayingView = findViewById(R.id.now_playing_fragment)
        bottomNavigationView = findViewById(R.id.bottom_navigation)

        val toolbar = findViewById<Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        host = supportFragmentManager
            .findFragmentById(R.id.nav_host_fragment) as NavHostFragment? ?: return

        val navController = host!!.navController

        appBarConfiguration = AppBarConfiguration(
            setOf(
                R.id.mainFragment,
                R.id.libraryFragment,
                R.id.favoritesFragment,
                R.id.managementFragment
            )
        )

        setupActionBar(navController, appBarConfiguration)

        bottomNavigationView?.setupWithNavController(navController)

        refreshManagementVisibility()

        navController.addOnDestinationChangedListener { _, destination, _ ->
            setsToggleItem?.isVisible = destination.id == R.id.mainFragment
            voiceMenuItem?.setShowAsAction(voiceMenuSlot(destination.id))
            val dest: String = try {
                resources.getResourceName(destination.id)
            } catch (_: Resources.NotFoundException) {
                destination.id.toString()
            }
            Timber.d("Navigated to $dest")

            currentFragmentId = destination.id
            // Handle the hiding of the NowPlaying fragment when the Player is active
            if (currentFragmentId == R.id.playerFragment) {
                hideNowPlaying()
            } else {
                if (!nowPlayingHidden) showNowPlaying()
            }
        }

        // Determine if this is a first run or LMS servers are not configured
        val showWelcomeScreen = UApp.instance!!.isFirstRun || Settings.staticPassword.isBlank()

        // This is a first run with only the demo entry inside the database
        // We set the active server to the demo one and show the welcome dialog
        if (showWelcomeScreen && !UApp.instance!!.setupDialogDisplayed) {
            showWelcomeDialog()
        } else if (Util.isVersionUpdate(this)) {
            Util.showChangelog(this, full = false)
        }

        // Ask for permission to send notifications
        Util.ensurePermissionToPostNotification(this)

        rxBusSubscription += RxBus.dismissNowPlayingCommandObservable.subscribe {
            nowPlayingHidden = true
            hideNowPlaying()
        }

        rxBusSubscription += RxBus.playerStateObservable.subscribe {
            if (it.state == STATE_READY) {
                showNowPlaying()
            } else {
                hideNowPlaying()
            }
        }

        rxBusSubscription += RxBus.themeChangedEventObservable.subscribe {
            recreate()
        }

        // The password can stop working while the app is happily running - it is changed on the
        // server, or an API key is revoked. Every screen then fails with an error it cannot fix,
        // so end the session and ask for credentials again instead of leaving a dead app open.
        rxBusSubscription += RxBus.authenticationFailureObservable.subscribe {
            if (!ActiveServerProvider.isOffline() && Settings.staticPassword.isNotBlank()) {
                logOut(R.string.welcome_session_expired)
            }
        }

        rxBusSubscription += RxBus.activeServerChangedObservable.subscribe {
            setMenuForServerCapabilities()
            updateOfflineBanner()
            checkMumaLogin()
        }

        // Setup app shortcuts on supported devices, but not on first start, when the server
        // is not configured yet.
        if (!UApp.instance!!.isFirstRun) {
            ShortcutUtil.registerShortcuts(this)
        }

        // Register our options menu
        addMenuProvider(
            searchMenuProvider,
            this,
            Lifecycle.State.RESUMED
        )

        lifecycleScope.launch {
            UpdateChecker.checkForUpdates(this@NavigationActivity)
        }
    }

    private val searchMenuProvider: MenuProvider = object : MenuProvider {
        override fun onPrepareMenu(menu: Menu) {
            setupSearchField(menu)
            menu.findItem(R.id.downloadsFragment)?.isVisible = !ActiveServerProvider.isOffline()
            setsToggleItem = menu.findItem(R.id.action_sets_toggle)
            setsToggleItem?.isVisible = currentFragmentId == R.id.mainFragment
            voiceMenuItem = menu.findItem(R.id.mumaVoiceFragment)
            voiceMenuItem?.setShowAsAction(voiceMenuSlot(currentFragmentId))
            setsToggle = setsToggleItem?.actionView?.findViewById(R.id.switch_sets)

            setsToggle?.let { toggle ->
                toggle.setOnCheckedChangeListener(null)
                toggle.isChecked = Settings.isSetsMode
                updateSetsToggleColors(toggle, Settings.isSetsMode)

                toggle.setOnCheckedChangeListener { _, isChecked ->
                    Settings.isSetsMode = isChecked
                    updateSetsToggleColors(toggle, isChecked)
                    RxBus.setsModeChangedPublisher.onNext(isChecked)
                }
            }
        }

        override fun onCreateMenu(menu: Menu, inflater: MenuInflater) {
            inflater.inflate(R.menu.search_view_menu, menu)
        }

        override fun onMenuItemSelected(item: MenuItem): Boolean {
            if (item.itemId == R.id.menu_exit) {
                setResult(Constants.RESULT_CLOSE_ALL)
                mediaPlayerManager.onDestroy()
                finish()
                exit()
                return true
            }
            if (item.itemId == R.id.menu_logout) {
                confirmLogout()
                return true
            }
            return item.onNavDestinationSelected(host!!.navController)
        }
    }

    private fun updateSetsToggleColors(toggle: MaterialSwitch, isSets: Boolean) {
        val brandColor = themeColor(androidx.appcompat.R.attr.colorPrimary)
        val states = arrayOf(
            intArrayOf(android.R.attr.state_checked),
            intArrayOf(-android.R.attr.state_checked)
        )
        val thumbColors = intArrayOf(brandColor, Color.WHITE)
        val trackColors = intArrayOf(brandColor.withAlpha(0x80), Color.DKGRAY)

        toggle.thumbTintList = ColorStateList(states, thumbColors)
        toggle.trackTintList = ColorStateList(states, trackColors)
    }

    private fun Int.withAlpha(alpha: Int): Int {
        return (this and 0x00FFFFFF) or (alpha shl 24)
    }

    fun setupSearchField(menu: Menu) {
        Timber.i("Recreating search field")
        val searchManager = getSystemService(SEARCH_SERVICE) as SearchManager
        val searchItem = menu.findItem(R.id.action_search)
        val searchView = searchItem.actionView as SearchView
        val searchableInfo = searchManager.getSearchableInfo(this.componentName)
        searchView.setSearchableInfo(searchableInfo)
        searchView.setIconifiedByDefault(false)

        if (searchQuery != null) {
            Timber.e("Found existing search query")
            searchItem.expandActionView()
            searchView.isIconified = false
            searchView.setQuery(searchQuery, false)
            searchView.clearFocus()
            // Restore search text only once!
            searchQuery = null
        }
    }

    override fun onResume() {
        Timber.d("onResume called")
        super.onResume()

        lifecycleScope.launch {
            UpdateChecker.checkForUpdates(this@NavigationActivity)
        }

        Storage.reset()

        lifecycleScope.launch(Dispatchers.IO) {
            Storage.checkForErrorsWithCustomRoot()
        }

        setMenuForServerCapabilities()
        updateOfflineBanner()
        // Logging in, logging out and switching servers all happen without recreating this
        // activity, so the admin answer from onCreate can be stale by now.
        refreshManagementVisibility()

        // Lifecycle support's constructor registers some event receivers so it should be created early
        lifecycleSupport.onCreate()

        if (!nowPlayingHidden) {
            showNowPlaying()
        } else {
            hideNowPlaying()
        }
    }

    /*
     * Attention: onDestroy does not mean that the app is necessarily being killed.
     * Also rotating the screen will call onDestroy() and then onCreate()
     */
    override fun onDestroy() {
        Timber.d("onDestroy called")
        rxBusSubscription.dispose()
        super.onDestroy()
    }

    private fun setupActionBar(navController: NavController, appBarConfig: AppBarConfiguration) {
        setupActionBarWithNavController(navController, appBarConfig)
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean = item.onNavDestinationSelected(findNavController(R.id.nav_host_fragment)) ||
        super.onOptionsItemSelected(item)

    // TODO: Why is this needed? Shouldn't it just work by default?
    override fun onSupportNavigateUp(): Boolean = findNavController(R.id.nav_host_fragment).navigateUp(appBarConfiguration)

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)

        when (intent.action) {
            Constants.INTENT_PLAY_RANDOM_SONGS -> {
                playRandomSongs()
            }
            Intent.ACTION_MAIN -> {
                if (intent.getBooleanExtra(Constants.INTENT_SHOW_PLAYER, false)) {
                    findNavController(R.id.nav_host_fragment).navigate(R.id.playerFragment)
                }
            }
            Intent.ACTION_SEARCH -> {
                searchQuery = intent.getStringExtra(SearchManager.QUERY)
                handleSearchIntent(searchQuery, false)
            }
            MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH -> {
                searchQuery = intent.getStringExtra(SearchManager.QUERY)
                handleSearchIntent(searchQuery, true)
            }
        }
    }

    private fun handleSearchIntent(query: String?, autoPlay: Boolean) {
        val suggestions = SearchRecentSuggestions(
            this,
            SearchSuggestionProvider.AUTHORITY,
            SearchSuggestionProvider.MODE
        )
        suggestions.saveRecentQuery(query, null)

        val action = NavigationGraphDirections.toSearchFragment(query, autoPlay)
        findNavController(R.id.nav_host_fragment).navigate(action)
    }

    private fun playRandomSongs() {
        val currentFragment = host?.childFragmentManager?.fragments?.last() ?: return
        val service = MusicServiceFactory.getMusicService()
        val musicDirectory = service.getRandomSongs(Settings.maxSongs)

        mediaPlayerManager.addToPlaylist(
            songs = musicDirectory.getTracks(),
            autoPlay = true,
            shuffle = false,
            insertionMode = MediaPlayerManager.InsertionMode.CLEAR
        )

        if (Settings.shouldTransitionOnPlayback) {
            currentFragment.findNavController().popBackStack(R.id.playerFragment, true)
            currentFragment.findNavController().navigate(R.id.playerFragment)
        }

        return
    }

    /**
     * Apply the customized language settings if needed
     */
    override fun attachBaseContext(newBase: Context?) {
        val locale = Settings.overrideLanguage
        val localizedContext: Context? = if (locale.isNotEmpty()) {
            LocaleHelper.wrap(newBase, locale)
        } else {
            newBase
        }

        // Apply the user's interface size on top, so the whole activity scales at once
        val scaledContext: ContextWrapper = UiScaleHelper.wrap(
            localizedContext,
            Settings.uiScalePercent
        )
        super.attachBaseContext(scaledContext)
    }

    private fun exit() {
        Timber.d("User choose to exit the app")

        // Broadcast that the service is being stopped
        RxBus.stopServiceCommandPublisher.onNext(Unit)

        // Broadcast that the app is being shutdown
        RxBus.shutdownCommandPublisher.onNext(Unit)

        finishAndRemoveTask()
    }

    /** Asks before logging out, because it stops playback and returns to the login screen. */
    private fun confirmLogout() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.logout_confirm_title)
            .setMessage(R.string.logout_confirm_message)
            .setPositiveButton(R.string.menu_logout) { _, _ -> logOut() }
            .setNegativeButton(R.string.common_cancel, null)
            .show()
    }

    /**
     * Ends the session and shows the login screen again.
     *
     * The username is deliberately kept: it is not a secret, it is prefilled on the login screen,
     * and the "are we logged in" check in [onCreate] keys off the password being blank. Everything
     * that can authenticate - the password, the MuMa API key and the stored MuMa tokens - is
     * cleared.
     */
    private fun logOut(@StringRes messageRes: Int? = null) {
        Timber.i("Logging out")

        // Whatever is playing was streamed with credentials that are about to be dropped.
        mediaPlayerManager.clear()

        Settings.staticPassword = ""
        Settings.mumaApiKey = ""
        Settings.mumaUserId = -1
        SecureSettings.clear()

        activeServerProvider.invalidateCache()
        MusicServiceFactory.resetMusicService()

        // The welcome dialog only shows itself once per app start; a fresh logout is exactly the
        // case where it must show itself again.
        UApp.instance!!.setupDialogDisplayed = false
        showWelcomeDialog(messageRes)
    }

    /**
     * Updates the welcome dialog's always-visible bottom status line. `reachable == null` means
     * "not checked yet" (the initial state, before the first probe completes).
     */
    private fun updateConnectivityStatus(statusText: TextView, reachable: Boolean?) {
        statusText.text = getString(
            when (reachable) {
                null -> R.string.welcome_status_checking
                true -> R.string.welcome_status_reachable
                false -> R.string.welcome_status_unreachable
            }
        )
    }

    /**
     * Shows the login screen. [messageRes], when given, is shown in the dialog's error slot before
     * the user has typed anything - that is how a logged-out session explains itself ("your
     * password was rejected") instead of silently reappearing at the login screen.
     */
    private fun showWelcomeDialog(@StringRes messageRes: Int? = null) {
        if (!UApp.instance!!.setupDialogDisplayed) {
            Settings.firstInstalledVersion = Util.getVersionCode(UApp.applicationContext())

            val view = LayoutInflater.from(this).inflate(R.layout.dialog_welcome, null)
            val usernameField = view.findViewById<TextInputEditText>(R.id.welcome_username)
            val passwordField = view.findViewById<TextInputEditText>(R.id.welcome_password)
            val progressBar = view.findViewById<ProgressBar>(R.id.welcome_progress)
            val errorText = view.findViewById<TextView>(R.id.welcome_error)
            val targetUrlText = view.findViewById<TextView>(R.id.welcome_target_url)
            val googleSignInButton = view.findViewById<MaterialButton>(R.id.welcome_google_signin)
            val skipButton = view.findViewById<ImageButton>(R.id.welcome_skip_button)
            val connectivityStatusText = view.findViewById<TextView>(R.id.welcome_connectivity_status)

            val dialog = MaterialAlertDialogBuilder(this, R.style.ThemeOverlay_Ultrasonic_WelcomeDialog)
                .setView(view)
                .setCancelable(false)
                .setPositiveButton(R.string.common_ok, null)
                .create()

            dialog.show()
            dialog.window?.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)

            // Signing out keeps the username, so someone signing back in only has to retype the
            // password.
            if (Settings.staticUserName.isNotBlank()) {
                usernameField.setText(Settings.staticUserName)
            }

            if (messageRes != null) {
                errorText.setText(messageRes)
                errorText.visibility = View.VISIBLE
            }

            // There is now only one, fixed production server (no more separate "alpha" server)
            val targetServer = ServerSettingsModel.STATIC_SERVERS.find { it.id == 0 }
            if (targetServer != null) {
                targetUrlText.text = getString(R.string.main_setup_server, targetServer.url)
                targetUrlText.visibility = View.VISIBLE
            }

            updateConnectivityStatus(connectivityStatusText, null)
            lifecycleScope.launch {
                val reachable = withContext(Dispatchers.IO) {
                    isServerReachable(targetServer?.url ?: ServerSettingsModel.SERVER_URL)
                }
                updateConnectivityStatus(connectivityStatusText, reachable)
            }

            dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val username = usernameField.text.toString()
                val password = passwordField.text.toString()

                if (username.isBlank() || password.isBlank()) {
                    errorText.text = getString(R.string.welcome_fields_required)
                    errorText.visibility = View.VISIBLE
                    return@setOnClickListener
                }

                progressBar.visibility = View.VISIBLE
                errorText.visibility = View.GONE

                usernameField.isEnabled = false
                passwordField.isEnabled = false
                dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).isEnabled = false
                googleSignInButton?.isEnabled = false

                lifecycleScope.launch {
                    val result = withContext(Dispatchers.IO) {
                        try {
                            // Update static credentials
                            Settings.staticUserName = username
                            Settings.staticPassword = password
                            activeServerProvider.invalidateCache()

                            withContext(Dispatchers.Main) {
                                activeServerProvider.setActiveServerById(0)
                            }

                            // Now test connection. Uses getOnlineMusicService() rather than
                            // getMusicService() deliberately: the latter can silently hand back
                            // the no-op OfflineMusicService (see its ping()) whenever
                            // "auto-switch offline" is enabled and isNetworkAvailable() reads
                            // false, even transiently/incorrectly - which would make this whole
                            // login test report "success" without ever having contacted the
                            // server.
                            MusicServiceFactory.resetMusicService()
                            val musicService = MusicServiceFactory.getOnlineMusicService()
                            musicService.ping()
                            true
                        } catch (e: Exception) {
                            Timber.e(e, "Connection test failed")
                            false
                        }
                    }

                    if (result) {
                        UApp.instance!!.setupDialogDisplayed = true
                        dialog.dismiss()
                        RxBus.loginSucceededPublisher.onNext(Unit)
                    } else {
                        // A failed ping() alone doesn't say whether the server was unreachable
                        // or the credentials were simply wrong - probe the server directly
                        // (no auth required) to tell the two apart instead of always blaming
                        // "your credentials", which sends people on a wild goose chase when the
                        // real problem is connectivity.
                        val reachable = withContext(Dispatchers.IO) {
                            isServerReachable(targetServer?.url ?: ServerSettingsModel.SERVER_URL)
                        }
                        updateConnectivityStatus(connectivityStatusText, reachable)
                        progressBar.visibility = View.GONE
                        errorText.text = getString(
                            // The probe above already proved the server answers, so a failed
                            // ping() here can only mean the credentials were rejected - saying
                            // "could not connect" instead sends people chasing a network
                            // problem that doesn't exist (see bug report 020).
                            if (reachable) R.string.welcome_invalid_credentials
                            else R.string.welcome_server_unreachable
                        )
                        errorText.visibility = View.VISIBLE
                        usernameField.isEnabled = true
                        passwordField.isEnabled = true
                        dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).isEnabled = true
                        googleSignInButton?.isEnabled = true
                    }
                }
            }

            googleSignInButton?.setOnClickListener {
                performWelcomeGoogleSignIn(
                    dialog = dialog,
                    progressBar = progressBar,
                    errorText = errorText,
                    usernameField = usernameField,
                    passwordField = passwordField,
                    googleSignInButton = googleSignInButton,
                    connectivityStatusText = connectivityStatusText
                )
            }

            // Deliberately secondary/de-emphasized (small icon, confirmation required) - this is
            // an escape hatch for when login is broken (server down, misconfigured Google OAuth
            // client, ...), not a normal part of the flow. Staying in offline mode never writes
            // Settings.staticUserName/staticPassword, so the existing "showWelcomeScreen" check in
            // onCreate (isFirstRun || Settings.staticPassword.isBlank()) already re-shows this
            // exact dialog on the next full app start, without any extra persisted flag.
            skipButton?.setOnClickListener {
                MaterialAlertDialogBuilder(this)
                    .setTitle(R.string.welcome_skip_confirm_title)
                    .setMessage(R.string.welcome_skip_confirm_message)
                    .setPositiveButton(R.string.welcome_skip_confirm_positive) { _, _ ->
                        activeServerProvider.setActiveServerById(ActiveServerProvider.OFFLINE_DB_ID)
                        UApp.instance!!.setupDialogDisplayed = true
                        dialog.dismiss()
                    }
                    .setNegativeButton(R.string.welcome_skip_confirm_negative, null)
                    .show()
            }
        }
    }

    /**
     * Lightweight, unauthenticated reachability probe used to tell a genuine network/server
     * problem apart from a login failure. Hits the Subsonic ping endpoint without credentials -
     * any HTTP response (even Subsonic's own "missing parameter" error) proves the server was
     * actually reached, so only a transport-level failure (DNS, timeout, connection refused, ...)
     * counts as "unreachable". Uses its own short timeouts so this never makes the welcome
     * dialog hang as long as the app's normal (60s) request timeout.
     */
    private fun isServerReachable(serverUrl: String): Boolean {
        val probeClient = subsonicAPIClient.okHttpClient.newBuilder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .build()
        val request = Request.Builder()
            .url("${serverUrl.removeSuffix("/")}/rest/ping.view?v=1.16.1&c=ultrasonic&f=json")
            .get()
            .build()
        return try {
            probeClient.newCall(request).execute().use { true }
        } catch (e: IOException) {
            Timber.w(e, "Server reachability probe failed")
            false
        }
    }

    /**
     * Handles "Sign in with Google" on the very first login screen (the welcome dialog).
     * Mirrors [nl.teunschriks.mumamobile.fragment.EditServerFragment.performMumaGoogleAuth]: on a
     * successful ("ok") response, the account's api_key is also accepted as a valid Subsonic/LMS
     * password (see /api/auth/login), so it is written into the username/password fields exactly
     * like the web frontend does, making Google login functionally identical to a manual login.
     * For a not-yet-linked/pending Google identity, this dismisses the welcome dialog and
     * navigates to the existing access-request flow ([nl.teunschriks.mumamobile.fragment.GoogleAuthFragment]).
     *
     * Note: at this point in a fresh install no server has been configured yet, so the
     * Koin-injected [subsonicAPIClient] (and its `mumaApi`) may still be pointing at the
     * offline/localhost fallback from [ActiveServerProvider]. A dedicated [MumaAPIClient] is
     * built here against the fixed production server address instead, so the request always
     * reaches the real Muma backend regardless of the app's current active-server state.
     */
    private fun performWelcomeGoogleSignIn(
        dialog: androidx.appcompat.app.AlertDialog,
        progressBar: ProgressBar,
        errorText: TextView,
        usernameField: TextInputEditText,
        passwordField: TextInputEditText,
        googleSignInButton: MaterialButton,
        connectivityStatusText: TextView
    ) {
        if (BuildConfig.GOOGLE_WEB_CLIENT_ID == "placeholder-id") {
            Timber.e("GOOGLE_WEB_CLIENT_ID is not configured! Google Sign-In will fail.")
        }
        val targetServer = ServerSettingsModel.STATIC_SERVERS.find { it.id == 0 }
        if (targetServer == null) {
            errorText.text = getString(R.string.background_task_network_error)
            errorText.visibility = View.VISIBLE
            return
        }
        val mumaBaseUrl = SubsonicAPIClient.mumaBaseUrlFor(targetServer.url)
        val welcomeMumaApi = MumaAPIClient(
            mumaBaseUrl,
            subsonicAPIClient.okHttpClient,
            nl.teunschriks.mumamobile.util.SecureSettings,
            debug = BuildConfig.DEBUG
        ).api

        val credentialManager = CredentialManager.create(this)
        // GetGoogleIdOption (even with setFilterByAuthorizedAccounts(false)) only reliably
        // surfaces a credential for accounts that have already signed into this app before -
        // for a first-time sign-in it throws NoCredentialException regardless of the device
        // having a real, usable Google account. GetSignInWithGoogleOption is Google's dedicated
        // option for this "not yet authorized" case and always shows the account chooser.
        val googleIdTokenRequest = GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdTokenRequest)
            .build()

        lifecycleScope.launch {
            val credential = try {
                credentialManager.getCredential(this@NavigationActivity, request).credential
            } catch (e: GetCredentialCancellationException) {
                return@launch
            } catch (e: NoCredentialException) {
                Timber.e(e, "Google Sign-In failed: No credentials available")
                errorText.text = getString(R.string.google_signin_no_accounts)
                errorText.visibility = View.VISIBLE
                return@launch
            } catch (e: Exception) {
                // Logged with the concrete exception class (not just the message) so a future
                // failure is diagnosable from `adb logcat` alone - e.g. telling a Play Services-
                // side "no credential issued" apart from a locally thrown parsing/IO error,
                // without needing a live repro session.
                Timber.e(e, "Google Sign-In failed: %s", e.javaClass.name)
                // This exception comes from Android's Credential Manager / Google Play
                // Services, not from our own server - but probing our server anyway tells the
                // user whether it's worth checking their connection at all, or whether the
                // problem is specific to Google Sign-In (misconfigured/expired OAuth client,
                // outdated Play Services, ...) and they should fall back to username/password.
                val reachable = withContext(Dispatchers.IO) { isServerReachable(targetServer.url) }
                updateConnectivityStatus(connectivityStatusText, reachable)
                errorText.text = if (reachable) {
                    // The exception class is also shown on screen, not only logged: the people
                    // who hit this are remote, non-technical users who can screenshot a dialog
                    // but will never run `adb logcat`, and without it every distinct cause
                    // (Play Services refusal, unregistered signing certificate, OAuth client
                    // misconfiguration) looks like the exact same message - see bug report 020.
                    getString(R.string.welcome_google_signin_failed_detail, e.javaClass.simpleName)
                } else {
                    getString(R.string.welcome_server_unreachable)
                }
                errorText.visibility = View.VISIBLE
                return@launch
            }

            // Credential Manager always returns third-party credential types (like Google's)
            // as a generic CustomCredential over the IPC boundary - it is never delivered as
            // the concrete GoogleIdTokenCredential subclass, even though that class extends
            // CustomCredential locally. It must be parsed explicitly via createFrom().
            val googleIdTokenCredential = if (
                credential is CustomCredential &&
                credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
            ) {
                try {
                    GoogleIdTokenCredential.createFrom(credential.data)
                } catch (e: GoogleIdTokenParsingException) {
                    Timber.e(e, "Failed to parse Google ID token credential")
                    null
                }
            } else {
                null
            }

            if (googleIdTokenCredential == null) {
                Timber.e("Google Sign-In returned an unexpected credential type: ${credential.javaClass.name}")
                // Purely a device-side parsing mismatch - our server was never contacted, so
                // there's nothing to probe and no "network" involved despite the generic name
                // of the fallback string.
                errorText.text = getString(R.string.welcome_google_signin_failed)
                errorText.visibility = View.VISIBLE
                return@launch
            }
            val idToken = googleIdTokenCredential.idToken

            progressBar.visibility = View.VISIBLE
            errorText.visibility = View.GONE

            // Short, user-presentable description of *why* the /api/auth/google call failed
            // (HTTP status or exception class), so the on-screen error can name the cause
            // instead of every backend-side failure looking identical - see bug report 020.
            var authFailureDetail: String? = null
            val authResult = withContext(Dispatchers.IO) {
                try {
                    val response = welcomeMumaApi.googleAuth(GoogleAuthRequest(idToken)).execute()
                    if (response.isSuccessful) {
                        response.body()
                    } else {
                        Timber.e(
                            "MuMa Google Auth failed: HTTP %d %s",
                            response.code(),
                            response.errorBody()?.string().orEmpty()
                        )
                        authFailureDetail = "HTTP ${response.code()}"
                        null
                    }
                } catch (e: Exception) {
                    Timber.e(e, "MuMa Google Auth failed: %s", e.javaClass.name)
                    authFailureDetail = e.javaClass.simpleName
                    null
                }
            }

            if (authResult == null) {
                progressBar.visibility = View.GONE
                // The call to our own /api/auth/google either threw or returned a non-2xx
                // status - probe the server (no auth needed) to tell a real outage/DNS/TLS
                // problem apart from e.g. an expired/misconfigured Google OAuth client, which
                // would fail here with the server otherwise being perfectly reachable.
                val reachable = withContext(Dispatchers.IO) { isServerReachable(targetServer.url) }
                updateConnectivityStatus(connectivityStatusText, reachable)
                val detail = authFailureDetail
                errorText.text = when {
                    !reachable -> getString(R.string.welcome_server_unreachable)
                    detail != null ->
                        getString(R.string.welcome_google_signin_failed_detail, detail)
                    else -> getString(R.string.welcome_google_signin_failed)
                }
                errorText.visibility = View.VISIBLE
                return@launch
            }

            when (authResult.status) {
                "ok" -> {
                    val username = authResult.user?.username
                    val apiKey = authResult.api_key ?: authResult.access_token
                    if (username == null || apiKey == null) {
                        // The server responded successfully, so this isn't a connectivity
                        // problem - it's a genuinely unexpected response shape.
                        progressBar.visibility = View.GONE
                        errorText.text = getString(R.string.welcome_google_signin_failed)
                        errorText.visibility = View.VISIBLE
                        return@launch
                    }

                    usernameField.setText(username)
                    passwordField.setText(apiKey)

                    // Unlike the manual username/password submit above, a successful "ok"
                    // response here already proves the credential is valid (verified
                    // server-side by Google + MuMa) - mirrors
                    // EditServerFragment.performMumaGoogleAuth() and the web frontend's
                    // handleGoogleResponse(), neither of which re-verify via a Subsonic ping
                    // before considering the sign-in successful. Gating on ping() here (as
                    // previously done, copied from the manual-entry flow above) meant a
                    // transient/unrelated connectivity hiccup on this first request could
                    // silently discard an otherwise-successful Google sign-in and leave the
                    // user stuck back at the login dialog.
                    withContext(Dispatchers.IO) {
                        try {
                            Settings.staticUserName = username
                            Settings.staticPassword = apiKey
                            activeServerProvider.invalidateCache()

                            withContext(Dispatchers.Main) {
                                activeServerProvider.setActiveServerById(0)
                            }

                            MusicServiceFactory.resetMusicService()
                        } catch (e: Exception) {
                            Timber.e(e, "Failed to activate server after Google Sign-In")
                        }
                    }

                    progressBar.visibility = View.GONE
                    UApp.instance!!.setupDialogDisplayed = true
                    dialog.dismiss()
                    RxBus.loginSucceededPublisher.onNext(Unit)
                }
                "unknown" -> {
                    progressBar.visibility = View.GONE
                    dialog.dismiss()
                    findNavController(R.id.nav_host_fragment).navigate(
                        NavigationGraphDirections.toGoogleAuthGlobal(
                            status = "unknown",
                            displayName = authResult.google?.display_name,
                            email = authResult.google?.email,
                            avatarUrl = authResult.google?.avatar_url,
                            idToken = idToken
                        )
                    )
                }
                "request_pending", "request_approved", "request_rejected" -> {
                    progressBar.visibility = View.GONE
                    dialog.dismiss()
                    findNavController(R.id.nav_host_fragment).navigate(
                        NavigationGraphDirections.toGoogleAuthGlobal(
                            status = authResult.status,
                            displayName = authResult.request?.display_name,
                            email = authResult.request?.email,
                            avatarUrl = authResult.request?.avatar_url,
                            idToken = idToken
                        )
                    )
                }
                else -> {
                    // Again, a successful response with an unrecognized status - not a
                    // connectivity issue. Naming the status makes an app/backend version skew
                    // (the only way to get here) recognizable from a screenshot.
                    Timber.e("MuMa Google Auth returned an unknown status: %s", authResult.status)
                    progressBar.visibility = View.GONE
                    errorText.text = getString(
                        R.string.welcome_google_signin_failed_detail,
                        authResult.status
                    )
                    errorText.visibility = View.VISIBLE
                    googleSignInButton.isEnabled = true
                }
            }
        }
    }

    private fun setUncaughtExceptionHandler() {
        val handler = Thread.getDefaultUncaughtExceptionHandler()
        if (handler !is UncaughtExceptionHandler) {
            Thread.setDefaultUncaughtExceptionHandler(UncaughtExceptionHandler(this))
        }
    }

    private fun showNowPlaying() {
        if (!Settings.showNowPlaying) {
            hideNowPlaying()
            return
        }

        // The logic for nowPlayingHidden is that the user can dismiss NowPlaying with a gesture,
        // and when the MediaPlayerService requests that it should be shown, it returns
        nowPlayingHidden = false
        // Do not show for Player fragment
        if (currentFragmentId == R.id.playerFragment) {
            hideNowPlaying()
            return
        }

        if (nowPlayingView != null) {
            val playerState: Int = mediaPlayerManager.playbackState
            if (playerState == STATE_BUFFERING || playerState == STATE_READY) {
                val item: MediaItem? = mediaPlayerManager.currentMediaItem
                if (item != null) {
                    nowPlayingView?.visibility = View.VISIBLE
                }
            } else {
                hideNowPlaying()
            }
        }
    }

    private fun hideNowPlaying() {
        nowPlayingView?.visibility = View.GONE
    }

    /**
     * The Beheer tab is hidden until music-manager confirms this key is an admin. It stays hidden
     * while the answer is pending or the check fails, so a slow or broken server never reveals it.
     *
     * Presentation only: every endpoint behind the tab is guarded by require_admin() server-side.
     */
    private fun refreshManagementVisibility() {
        lifecycleScope.launch {
            val isAdmin = managementRepository.isAdmin()
            bottomNavigationView?.menu?.findItem(R.id.managementFragment)?.isVisible = isAdmin
        }
    }

    private fun setMenuForServerCapabilities() {
        // The bottom bar used to hide the Playlists item when offline, because server playlists
        // are useless without a connection. Playlists now live inside the Library tab alongside
        // artists and albums, which do work offline from the cache, so nothing is hidden there.

        // Refreshes the toolbar overflow menu so the downloadsFragment isOnline check in
        // searchMenuProvider.onPrepareMenu (above) re-runs with the new state.
        invalidateOptionsMenu()
    }

    /**
     * Keeps the app-wide "you're in offline mode" banner (added below the toolbar in
     * navigation_activity.xml) in sync with the active server. Works regardless of *how* offline
     * mode was entered - the welcome dialog's skip button, or the existing manual "Offline" entry
     * in the server selector - since both go through the same ActiveServerProvider mechanism.
     */
    private fun updateOfflineBanner() {
        findViewById<TextView>(R.id.offline_mode_banner)?.apply {
            visibility = if (ActiveServerProvider.isOffline()) View.VISIBLE else View.GONE
            setOnClickListener { showWelcomeDialog() }
        }
    }

    private fun checkMumaLogin() {
        val activeServer = activeServerProvider.getActiveServer()
        if (!ActiveServerProvider.isOffline() && activeServer.apiKey.isNullOrEmpty() &&
            (activeServer.mumaUserId == null || activeServer.mumaUserId == -1)) {
            lifecycleScope.launch(Dispatchers.IO) {
                try {
                    MusicServiceFactory.getMusicService().mumaLogin()
                } catch (e: Exception) {
                    Timber.e(e, "Failed to auto-fetch MuMa key")
                }
                // The onCreate visibility check ran without a key, so it answered "not an admin".
                // Now that there is one, ask again.
                withContext(Dispatchers.Main) { refreshManagementVisibility() }
            }
        }
    }
}

/**
 * Where the microphone is worth a toolbar slot.
 *
 * @details The activity's own menu is inflated on top of every screen and claims the action slots
 * before a fragment's menu is prepared, so an "ifRoom" microphone silently pushed the track
 * collection's "Play all" into the overflow. Almost every screen has room to spare, and the manual
 * tells the reader the microphone is in the toolbar, so it keeps its icon by default and steps
 * back into the overflow only on the screens whose own actions need the room. The player owns
 * actions too and still shows it: a queue is exactly where the next request gets spoken.
 */
internal fun voiceMenuSlot(destinationId: Int): Int =
    when (destinationId) {
        R.id.trackCollectionFragment, R.id.logViewerFragment -> MenuItem.SHOW_AS_ACTION_NEVER
        else -> MenuItem.SHOW_AS_ACTION_ALWAYS
    }
