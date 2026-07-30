/*
 * NavigationActivity.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package org.moire.ultrasonic.activity

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
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
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
import androidx.core.content.ContextCompat
import androidx.core.view.GravityCompat
import androidx.core.view.MenuProvider
import androidx.drawerlayout.widget.DrawerLayout
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
import com.google.android.material.navigation.NavigationView
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
import org.moire.ultrasonic.BuildConfig
import org.moire.ultrasonic.NavigationGraphDirections
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.muma.GoogleAuthRequest
import org.moire.ultrasonic.api.muma.MumaAPIClient
import org.moire.ultrasonic.api.subsonic.SubsonicAPIClient
import org.moire.ultrasonic.app.UApp
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.data.ServerSetting
import org.moire.ultrasonic.data.ServerSettingDao
import org.moire.ultrasonic.model.ServerSettingsModel
import org.moire.ultrasonic.provider.SearchSuggestionProvider
import org.moire.ultrasonic.service.MediaPlayerLifecycleSupport
import org.moire.ultrasonic.service.MediaPlayerManager
import org.moire.ultrasonic.service.MusicServiceFactory
import org.moire.ultrasonic.service.RxBus
import org.moire.ultrasonic.service.plusAssign
import org.moire.ultrasonic.util.Constants
import org.moire.ultrasonic.util.LocaleHelper
import org.moire.ultrasonic.util.ServerColor
import org.moire.ultrasonic.util.Settings
import org.moire.ultrasonic.util.ShortcutUtil
import org.moire.ultrasonic.util.Storage
import org.moire.ultrasonic.util.UncaughtExceptionHandler
import org.moire.ultrasonic.util.UpdateChecker
import org.moire.ultrasonic.util.Util
import timber.log.Timber

/**
 * The main (and only) Activity of Ultrasonic which loads all other screens as Fragments.
 * Because this is the only Activity we have to manage the apps lifecycle through this activity
 * onCreate/onResume/onDestroy methods...
 */
@Suppress("TooManyFunctions")
class NavigationActivity : ScopeActivity() {
    private var videoMenuItem: MenuItem? = null
    private var chatMenuItem: MenuItem? = null
    private var bookmarksMenuItem: MenuItem? = null
    private var sharesMenuItem: MenuItem? = null
    private var podcastsMenuItem: MenuItem? = null
    private var playlistsMenuItem: MenuItem? = null
    private var downloadsMenuItem: MenuItem? = null
    private var setsToggleItem: MenuItem? = null

    private var nowPlayingView: FragmentContainerView? = null
    private var nowPlayingHidden = false
    private var navigationView: NavigationView? = null
    private var bottomNavigationView: BottomNavigationView? = null
    private var drawerLayout: DrawerLayout? = null
    private var host: NavHostFragment? = null
    private var selectServerButton: MaterialButton? = null
    private var dropDownButton: MaterialButton? = null
    private var headerBackgroundImage: ImageView? = null
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
    private val serverRepository: ServerSettingDao by inject()
    private val subsonicAPIClient: SubsonicAPIClient by inject()

    private var currentFragmentId: Int = 0
    private var cachedServerCount: Int = 0

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
        navigationView = findViewById(R.id.nav_view)
        bottomNavigationView = findViewById(R.id.bottom_navigation)
        drawerLayout = findViewById(R.id.drawer_layout)

        setupDrawerLayout(drawerLayout!!)

        val toolbar = findViewById<Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        host = supportFragmentManager
            .findFragmentById(R.id.nav_host_fragment) as NavHostFragment? ?: return

        val navController = host!!.navController

        appBarConfiguration = AppBarConfiguration(
            setOf(
                R.id.mainFragment,
                R.id.mediaLibraryFragment,
                R.id.searchFragment,
                R.id.playlistsFragment,
                R.id.downloadsFragment,
                R.id.sharesFragment,
                R.id.bookmarksFragment,
                R.id.chatFragment,
                R.id.podcastFragment,
                R.id.settingsFragment,
                R.id.aboutFragment,
                R.id.playerFragment
            ),
            drawerLayout
        )

        setupActionBar(navController, appBarConfiguration)

        setupNavigationMenu(navController)
        bottomNavigationView?.setupWithNavController(navController)

        navController.addOnDestinationChangedListener { _, destination, _ ->
            setsToggleItem?.isVisible = destination.id == R.id.mainFragment
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

        rxBusSubscription += RxBus.activeServerChangedObservable.subscribe {
            updateNavigationHeaderForServer()
            setMenuForServerCapabilities()
            checkMumaLogin()
        }

        serverRepository.liveServerCount().observe(this) { count ->
            cachedServerCount = count ?: 0
            updateNavigationHeaderForServer()
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
            setsToggleItem = menu.findItem(R.id.action_sets_toggle)
            setsToggleItem?.isVisible = currentFragmentId == R.id.mainFragment
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
            return item.onNavDestinationSelected(host!!.navController)
        }
    }

    private fun updateSetsToggleColors(toggle: MaterialSwitch, isSets: Boolean) {
        val brandColor = getColor(R.color.spotify_green)
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

    private fun setupDrawerLayout(drawerLayout: DrawerLayout) {
        // Set initial state passed on drawer state
        closeNavigationDrawerOnBack.isEnabled = drawerLayout.isOpen

        // Add the back press listener
        onBackPressedDispatcher.addCallback(this, closeNavigationDrawerOnBack)

        // Listen to changes in the drawer state and enable the back press listener accordingly.
        drawerLayout.addDrawerListener(object : DrawerLayout.DrawerListener {
            override fun onDrawerSlide(drawerView: View, slideOffset: Float) {
                // Nothing
            }

            override fun onDrawerOpened(drawerView: View) {
                closeNavigationDrawerOnBack.isEnabled = true
            }

            override fun onDrawerClosed(drawerView: View) {
                closeNavigationDrawerOnBack.isEnabled = false
            }

            override fun onDrawerStateChanged(newState: Int) {
                // Nothing
            }
        })
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

    private fun updateNavigationHeaderForServer() {
        val showVectorBackground = false

        val activeServer = activeServerProvider.getActiveServer()

        if (cachedServerCount == 0) {
            selectServerButton?.text = getString(R.string.main_setup_server, activeServer.name)
        } else {
            selectServerButton?.text = activeServer.name
        }

        val foregroundColor =
            ServerColor.getForegroundColor(this, activeServer.color, showVectorBackground)
        val backgroundColor =
            ServerColor.getBackgroundColor(this, activeServer.color)

        if (activeServer.index == 0) {
            selectServerButton?.icon =
                ContextCompat.getDrawable(this, R.drawable.ic_menu_screen_on_off)
        } else {
            selectServerButton?.icon =
                ContextCompat.getDrawable(this, R.drawable.ic_menu_select_server)
        }

        selectServerButton?.iconTint = ColorStateList.valueOf(foregroundColor)
        selectServerButton?.setTextColor(foregroundColor)
        dropDownButton?.iconTint = ColorStateList.valueOf(foregroundColor)
        headerBackgroundImage?.setBackgroundColor(backgroundColor)

        // Hide the vector graphic on Android 12 or later
        if (!showVectorBackground) {
            headerBackgroundImage?.setImageDrawable(null)
        }
    }

    private fun setupNavigationMenu(navController: NavController) {
        navigationView?.setupWithNavController(navController)

        // The fragments which expect SafeArgs need to be navigated to with SafeArgs (even when
        // they are empty)!
        navigationView?.setNavigationItemSelectedListener {
            when (it.itemId) {
                R.id.mediaLibraryFragment -> {
                    navController.navigate(NavigationGraphDirections.toMediaLibrary())
                }
                R.id.bookmarksFragment -> {
                    navController.navigate(NavigationGraphDirections.toBookmarks())
                }
                R.id.trackCollectionFragment -> {
                    navController.navigate(
                        NavigationGraphDirections.toTrackCollection(
                            getVideos = true
                        )
                    )
                }
                R.id.menu_exit -> {
                    setResult(Constants.RESULT_CLOSE_ALL)
                    mediaPlayerManager.onDestroy()
                    finish()
                    exit()
                }
                else -> navController.navigate(it.itemId)
            }
            drawerLayout?.closeDrawer(GravityCompat.START)
            true
        }

        chatMenuItem = navigationView?.menu?.findItem(R.id.chatFragment)
        bookmarksMenuItem = navigationView?.menu?.findItem(R.id.bookmarksFragment)
        sharesMenuItem = navigationView?.menu?.findItem(R.id.sharesFragment)
        podcastsMenuItem = navigationView?.menu?.findItem(R.id.podcastFragment)
        playlistsMenuItem = navigationView?.menu?.findItem(R.id.playlistsFragment)
        downloadsMenuItem = navigationView?.menu?.findItem(R.id.downloadsFragment)
        videoMenuItem = navigationView?.menu?.findItem(R.id.trackCollectionFragment)

        selectServerButton =
            navigationView?.getHeaderView(0)?.findViewById(R.id.header_select_server)
        dropDownButton =
            navigationView?.getHeaderView(0)?.findViewById(R.id.edit_server_button)

        val onClick: (View) -> Unit = {
            if (drawerLayout?.isDrawerVisible(GravityCompat.START) == true) {
                this.drawerLayout?.closeDrawer(GravityCompat.START)
            }
            navController.navigate(R.id.serverSelectorFragment)
        }

        selectServerButton?.setOnClickListener(onClick)
        dropDownButton?.setOnClickListener(onClick)

        headerBackgroundImage =
            navigationView?.getHeaderView(0)?.findViewById(R.id.img_header_bg)
    }

    private fun setupActionBar(navController: NavController, appBarConfig: AppBarConfiguration) {
        setupActionBarWithNavController(navController, appBarConfig)
    }

    private val closeNavigationDrawerOnBack = object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            drawerLayout?.closeDrawer(GravityCompat.START)
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        val retValue = super.onCreateOptionsMenu(menu)
        if (navigationView == null) {
            menuInflater.inflate(R.menu.navigation_drawer, menu)
            return true
        }
        return retValue
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
        if (locale.isNotEmpty()) {
            val localeUpdatedContext: ContextWrapper = LocaleHelper.wrap(newBase, locale)
            super.attachBaseContext(localeUpdatedContext)
        } else {
            super.attachBaseContext(newBase)
        }
    }

    private fun exit() {
        Timber.d("User choose to exit the app")

        // Broadcast that the service is being stopped
        RxBus.stopServiceCommandPublisher.onNext(Unit)

        // Broadcast that the app is being shutdown
        RxBus.shutdownCommandPublisher.onNext(Unit)

        finishAndRemoveTask()
    }

    private fun showWelcomeDialog() {
        if (!UApp.instance!!.setupDialogDisplayed) {
            Settings.firstInstalledVersion = Util.getVersionCode(UApp.applicationContext())

            val view = LayoutInflater.from(this).inflate(R.layout.dialog_welcome, null)
            val usernameField = view.findViewById<TextInputEditText>(R.id.welcome_username)
            val passwordField = view.findViewById<TextInputEditText>(R.id.welcome_password)
            val progressBar = view.findViewById<ProgressBar>(R.id.welcome_progress)
            val errorText = view.findViewById<TextView>(R.id.welcome_error)
            val targetUrlText = view.findViewById<TextView>(R.id.welcome_target_url)
            val googleSignInButton = view.findViewById<MaterialButton>(R.id.welcome_google_signin)

            val dialog = MaterialAlertDialogBuilder(this)
                .setTitle(R.string.welcome_title)
                .setView(view)
                .setCancelable(false)
                .setPositiveButton(R.string.common_ok, null)
                .create()

            dialog.show()

            // There is now only one, fixed production server (no more separate "alpha" server)
            val targetServer = ServerSettingsModel.STATIC_SERVERS.find { it.id == 0 }
            if (targetServer != null) {
                targetUrlText.text = getString(R.string.main_setup_server, targetServer.url)
                targetUrlText.visibility = View.VISIBLE
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

                            // Now test connection
                            MusicServiceFactory.resetMusicService()
                            val musicService = MusicServiceFactory.getMusicService()
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
                    } else {
                        // A failed ping() alone doesn't say whether the server was unreachable
                        // or the credentials were simply wrong - probe the server directly
                        // (no auth required) to tell the two apart instead of always blaming
                        // "your credentials", which sends people on a wild goose chase when the
                        // real problem is connectivity.
                        val reachable = withContext(Dispatchers.IO) {
                            isServerReachable(targetServer?.url ?: ServerSettingsModel.LMS_URL)
                        }
                        progressBar.visibility = View.GONE
                        errorText.text = getString(
                            if (reachable) R.string.welcome_connection_failed
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
                    googleSignInButton = googleSignInButton
                )
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
     * Mirrors [org.moire.ultrasonic.fragment.EditServerFragment.performMumaGoogleAuth]: on a
     * successful ("ok") response, the account's api_key is also accepted as a valid Subsonic/LMS
     * password (see /api/auth/login), so it is written into the username/password fields exactly
     * like the web frontend does, making Google login functionally identical to a manual login.
     * For a not-yet-linked/pending Google identity, this dismisses the welcome dialog and
     * navigates to the existing access-request flow ([org.moire.ultrasonic.fragment.GoogleAuthFragment]).
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
        googleSignInButton: MaterialButton
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
            org.moire.ultrasonic.util.SecureSettings,
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
                Timber.e(e, "Google Sign-In failed")
                // This exception comes from Android's Credential Manager / Google Play
                // Services, not from our own server - but probing our server anyway tells the
                // user whether it's worth checking their connection at all, or whether the
                // problem is specific to Google Sign-In (misconfigured/expired OAuth client,
                // outdated Play Services, ...) and they should fall back to username/password.
                val reachable = withContext(Dispatchers.IO) { isServerReachable(targetServer.url) }
                errorText.text = getString(
                    if (reachable) R.string.welcome_google_signin_failed
                    else R.string.welcome_server_unreachable
                )
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

            val authResult = withContext(Dispatchers.IO) {
                try {
                    val response = welcomeMumaApi.googleAuth(GoogleAuthRequest(idToken)).execute()
                    if (response.isSuccessful) response.body() else null
                } catch (e: Exception) {
                    Timber.e(e, "MuMa Google Auth failed")
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
                errorText.text = getString(
                    if (reachable) R.string.welcome_google_signin_failed
                    else R.string.welcome_server_unreachable
                )
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
                    // connectivity issue.
                    progressBar.visibility = View.GONE
                    errorText.text = getString(R.string.welcome_google_signin_failed)
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

    private fun setMenuForServerCapabilities() {
        val isOnline = !ActiveServerProvider.isOffline()
        val activeServer = activeServerProvider.getActiveServer()

        // Note: Offline capabilities are defined in ActiveServerProvider, OFFLINE_DB.
        // If you add Offline support for some of these features you need
        // to switch the boolean to true there.
        chatMenuItem?.isVisible = activeServer.chatSupport != false
        bookmarksMenuItem?.isVisible = activeServer.bookmarkSupport != false
        sharesMenuItem?.isVisible = activeServer.shareSupport != false
        podcastsMenuItem?.isVisible = activeServer.podcastSupport != false
        playlistsMenuItem?.isVisible = isOnline
        downloadsMenuItem?.isVisible = isOnline
        videoMenuItem?.isVisible = activeServer.videoSupport != false
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
            }
        }
    }
}
