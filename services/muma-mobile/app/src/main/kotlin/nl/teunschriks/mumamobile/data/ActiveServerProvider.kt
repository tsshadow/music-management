/*
 * ActiveServerProvider.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import androidx.room.Room
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient.Companion.OFFLINE_DB_URL
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.di.DB_FILENAME
import nl.teunschriks.mumamobile.model.ServerSettingsModel
import nl.teunschriks.mumamobile.service.MusicServiceFactory.resetMusicService
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.util.Constants
import nl.teunschriks.mumamobile.util.SecureSettings
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util
import timber.log.Timber

/**
 * This class can be used to retrieve the properties of the Active Server
 * It caches the settings read up from the DB to improve performance.
 */
class ActiveServerProvider(private val repository: ServerSettingDao) : CoroutineScope by CoroutineScope(Dispatchers.IO) {
    private var cachedServer: ServerSetting? = null
    private var cachedDatabase: MetaDatabase? = null
    private var cachedServerId: Int? = null

    /**
     * Get the settings of the current Active Server
     * @return The Active Server Settings
     */
    @JvmOverloads
    fun getActiveServer(serverId: Int = getActiveServerId()): ServerSetting {
        if (serverId > OFFLINE_DB_ID) {
            if (cachedServer != null && cachedServer!!.id == serverId) return cachedServer!!

            // Get from static list in ServerSettingsModel
            cachedServer = nl.teunschriks.mumamobile.model.ServerSettingsModel.STATIC_SERVERS.find { it.id == serverId }?.copy(
                userName = Settings.staticUserName,
                password = Settings.staticPassword
            )

            if (cachedServer != null) {
                Timber.d("getActiveServer retrieved from static list, id: %s", serverId)
                return cachedServer!!
            }

            // Fallback to Offline
            setActiveServerById(OFFLINE_DB_ID)
        }

        return OFFLINE_DB
    }

    /**
     * Resolves the index (sort order) of a server to its id (unique)
     * @param index: The index of the server in the server selector
     * @return id: The unique id of the server
     */
    fun getServerIdFromIndex(index: Int): Int {
        if (index <= OFFLINE_DB_INDEX) {
            // Offline mode is selected
            return OFFLINE_DB_ID
        }

        return nl.teunschriks.mumamobile.model.ServerSettingsModel.STATIC_SERVERS.find { it.index == index }?.id ?: 0
    }

    /**
     * Sets the Active Server by the Server Index in the Server Selector List
     * @param index: The index of the Active Server in the Server Selector List
     */
    fun setActiveServerByIndex(index: Int) {
        Timber.d("setActiveServerByIndex $index")
        if (index <= OFFLINE_DB_INDEX) {
            // Offline mode is selected
            setActiveServerById(OFFLINE_DB_ID)
            return
        }

        val serverId = nl.teunschriks.mumamobile.model.ServerSettingsModel.STATIC_SERVERS.find { it.index == index }?.id ?: 0
        setActiveServerById(serverId)
    }

    /**
     * Sets the Active Server by its unique id
     * @param serverId: The id of the desired server
     */
    fun setActiveServerById(serverId: Int) {
        val oldServerId = Settings.activeServer
        if (oldServerId == serverId) return

        if (oldServerId != OFFLINE_DB_ID && serverId == OFFLINE_DB_ID) {
            Util.toast(R.string.server_switched_offline, true, UApp.applicationContext())
        } else if (oldServerId == OFFLINE_DB_ID && serverId != OFFLINE_DB_ID) {
            Util.toast(R.string.server_switched_online, true, UApp.applicationContext())
        }

        // Notify components about the change before actually resetting the MusicService
        // so they can react by e.g. stopping playback on the old server
        RxBus.activeServerChangingPublisher.onNext(oldServerId)

        Settings.activeServer = serverId
        resetMusicService()

        // Use a coroutine to post the server change to the end of the message queue
        launch {
            withContext(Dispatchers.Main) {
                RxBus.activeServerChangedPublisher.onNext(getActiveServer(serverId))
                Timber.i("setActiveServerById done, new id: %s", serverId)
            }
        }
    }

    @Synchronized
    fun getActiveMetaDatabase(): MetaDatabase {
        val activeServer = getActiveServerId()

        if (activeServer == cachedServerId && cachedDatabase != null) {
            return cachedDatabase!!
        }

        if (activeServer < 1) {
            return offlineMetaDatabase
        }

        Timber.i("Switching to new database, id:$activeServer")
        cachedServerId = activeServer
        cachedDatabase = initDatabase(activeServer)

        return cachedDatabase!!
    }

    val offlineMetaDatabase: MetaDatabase by lazy {
        initDatabase(0)
    }

    private fun initDatabase(serverId: Int): MetaDatabase = Room.databaseBuilder(
        UApp.applicationContext(),
        MetaDatabase::class.java,
        METADATA_DB + serverId
    )
        .addMigrations(META_MIGRATION_2_3)
        .addMigrations(META_MIGRATION_3_4)
        .addMigrations(META_MIGRATION_4_5)
        .addMigrations(META_MIGRATION_5_6)
        .addMigrations(META_MIGRATION_6_7)
        .addMigrations(META_MIGRATION_7_8)
        .addMigrations(META_MIGRATION_8_9)
        .fallbackToDestructiveMigrationOnDowngrade()
        .build()

    @Synchronized
    fun deleteMetaDatabase(id: Int) {
        cachedDatabase?.close()
        UApp.applicationContext().deleteDatabase(METADATA_DB + id)
        Timber.i("Deleted metadataBase, id:$id")
    }

    /**
     * Sets the minimum Subsonic API version of the current server.
     */
    fun setMinimumApiVersion(apiVersion: String) {
        cachedServer?.minimumApiVersion = apiVersion
    }

    fun setMumaSettings(apiKey: String, userId: Int?) {
        // Sync globally
        Settings.mumaApiKey = apiKey
        // Only update MuMa ID if the stored one cannot be real, and only with one that can. A 0 --
        // Gson's default for an id the response did not carry -- is not the -1 "unknown" sentinel,
        // so it passed every guard and every per-user call went to a user that is not there. Any
        // device that already stored a 0 is repaired by the next login for the same reason.
        if (!isUsableMumaUserId(Settings.mumaUserId) && isUsableMumaUserId(userId)) {
            Settings.mumaUserId = userId!!
        }
    }

    fun update(serverSetting: ServerSetting) {
        if (serverSetting.id > OFFLINE_DB_ID) {
            Settings.staticUserName = serverSetting.userName
            Settings.staticPassword = serverSetting.password
            invalidateCache()
            launch(Dispatchers.Main) {
                resetMusicService()
            }
        }
    }

    /**
     * The one server the app can sign in to, whatever the active selection is.
     *
     * "Offline" (the default on a fresh install, and what the legacy UI switches to when the
     * network is gone) is a mode rather than a server: its url is `http://localhost`, which is
     * also the origin the Capacitor WebView serves the bundle from. A shell that built its
     * requests on it would ask its own page for `/rest/ping` and get index.html back, so the
     * shell reads the real server from here instead of from [getActiveServer].
     */
    fun signInServer(): ServerSetting = ServerSettingsModel.STATIC_SERVERS.first().copy(
        userName = Settings.staticUserName,
        password = Settings.staticPassword
    )

    /**
     * Persists a signed-in username/password pair, e.g. from the Capacitor shell's web login
     * screen, so downloads, Android Auto and the legacy UI see the same session. Goes through
     * [update] -- the same path the server-selector settings screen uses -- rather than writing
     * [Settings] a second way. There is one server in static mode (see
     * [nl.teunschriks.mumamobile.model.ServerSettingsModel.STATIC_SERVERS]), so its url is fixed
     * and only the credentials move.
     *
     * Written against [signInServer], not [getActiveServer]: on a fresh install the active server
     * is Offline, [update] ignores that id, and the pair the listener just typed would be lost.
     * The server is then made active as well, which is what the legacy login dialog does
     * (`NavigationActivity`) and what the next boot's `credentials()` relies on.
     */
    fun saveCredentials(username: String, password: String) {
        val server = signInServer()
        update(server.copy(userName = username, password = password))
        if (getActiveServerId() == OFFLINE_DB_ID) setActiveServerById(server.id)
    }

    /**
     * Clears everything that can authenticate: the static password, the muma API key/user id and
     * the encrypted muma tokens in [SecureSettings]. The username is kept -- it is not a secret,
     * and it is what the next sign-in prefills. This is the same clearing `NavigationActivity`'s
     * logout menu already did; both now call this so there is one definition of "signed out".
     * Callers that hold a [nl.teunschriks.mumamobile.service.MediaPlayerManager] still have to
     * clear its queue themselves -- that is not this class's job. Downloaded files are untouched.
     */
    fun signOut() {
        Settings.staticPassword = ""
        Settings.mumaApiKey = ""
        Settings.mumaUserId = -1
        SecureSettings.clear()
        invalidateCache()
        resetMusicService()
    }

    /**
     * Invalidates the Active Server Setting cache
     * This should be called when the Active Server or one of its properties changes
     */
    fun invalidateCache() {
        Timber.d("Cache is invalidated")
        cachedServer = null
    }

    /**
     * Gets the Rest Url of the Active Server
     * @param method: The Rest resource to use
     * @return The Rest Url of the method on the server
     */
    fun getRestUrl(method: String?): String {
        val builder = StringBuilder(8192)
        val activeServer = getActiveServer()
        val serverUrl: String = activeServer.url
        val username: String = activeServer.userName
        var password: String = activeServer.password

        // Slightly obfuscate password
        password = "enc:" + Util.utf8HexEncode(password)
        builder.append(serverUrl)
        if (builder[builder.length - 1] != '/') {
            builder.append('/')
        }
        builder.append("rest/").append(method).append(".view")
        builder.append("?u=").append(username)
        builder.append("&p=").append(password)
        builder.append("&v=").append(Constants.REST_PROTOCOL_VERSION)
        builder.append("&c=").append(Constants.REST_CLIENT_ID)
        return builder.toString()
    }

    companion object {
        const val METADATA_DB = "$DB_FILENAME-meta-"
        const val OFFLINE_DB_ID = -1

        // There is now only one static server (LMS, index 0) - no more separate "alpha" server -
        // so Offline moves down to index 1 (was 2, when LMS=0/alpha=1/offline=2).
        const val OFFLINE_DB_INDEX = 1

        val OFFLINE_DB = ServerSetting(
            id = OFFLINE_DB_ID,
            index = OFFLINE_DB_INDEX,
            name = UApp.applicationContext().getString(R.string.main_offline),
            url = OFFLINE_DB_URL,
            userName = "",
            password = "",
            jukeboxByDefault = false,
            allowSelfSignedCertificate = false,
            forcePlainTextPassword = false,
            musicFolderId = "",
            minimumApiVersion = null,
            bookmarkSupport = false,
            podcastSupport = false,
            shareSupport = false,
            chatSupport = false,
            videoSupport = false,
            jukeboxSupport = false
        )

        /**
         * Queries if the Active Server is the "Offline" mode of Ultrasonic
         * @return True, if the "Offline" mode is selected
         */
        fun isOffline(): Boolean = getActiveServerId() == OFFLINE_DB_ID

        /**
         * Queries the Id of the Active Server
         */
        fun getActiveServerId(): Int = Settings.activeServer

        /**
         * Queries if Scrobbling is enabled
         */
        fun isScrobblingEnabled(): Boolean {
            if (isOffline()) {
                return false
            }
            return Settings.scrobbleEnabled
        }

        /**
         * Queries if ID3 tags should be used
         */
        fun shouldUseId3Tags(): Boolean = Settings.id3TagsEnabledOnline && (!isOffline() || Settings.id3TagsEnabledOffline)

        /**
         * Queries if Server Scaling is enabled
         */
        fun isServerScalingEnabled(): Boolean {
            if (isOffline()) {
                return false
            }
            return Settings.serverScaling
        }
    }
}
