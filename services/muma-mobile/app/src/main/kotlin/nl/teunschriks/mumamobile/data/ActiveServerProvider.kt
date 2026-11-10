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
class ActiveServerProvider : CoroutineScope by CoroutineScope(Dispatchers.IO) {
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

            // Get from the static list
            // No password: none is stored after a sign-in any more (issue #101).
            cachedServer = StaticServers.servers().find { it.id == serverId }?.copy(
                userName = Settings.staticUserName
            )

            if (cachedServer != null) {
                Timber.d("getActiveServer retrieved from static list, id: %s", serverId)
                return cachedServer!!
            }

            // Fallback to Offline; also what an install without a stored address gets.
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

        return StaticServers.servers().find { it.index == index }?.id ?: 0
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

        val serverId = StaticServers.servers().find { it.index == index }?.id ?: 0
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
        .addMigrations(META_MIGRATION_9_10)
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
        // Sync globally; encrypted (issue #115)
        SecureSettings.mumaApiKey = apiKey
        // Only update MuMa ID if the stored one cannot be real, and only with one that can. A 0 --
        // Gson's default for an id the response did not carry -- is not the -1 "unknown" sentinel,
        // so it passed every guard and every per-user call went to a user that is not there. Any
        // device that already stored a 0 is repaired by the next login for the same reason.
        if (!isUsableMumaUserId(Settings.mumaUserId) && isUsableMumaUserId(userId)) {
            Settings.mumaUserId = userId!!
        }
    }

    /**
     * Stores the account's own spelling of the user name after MuMa returned it. Deliberately not
     * through [update]: the session is still valid, so there is no reason to reset the music
     * service in the middle of the call that learned the spelling -- the next client built from
     * the settings signs with it. See [SubsonicSigning.adopt].
     */
    fun adoptCanonicalUserName(userName: String) {
        if (userName.isBlank() || userName == Settings.staticUserName) return
        Settings.staticUserName = userName
        invalidateCache()
    }

    /**
     * Stores the user name of [serverSetting] and rebuilds the music service. Its password is
     * ignored: none is kept after a sign-in (issue #101).
     */
    fun update(serverSetting: ServerSetting) {
        if (serverSetting.id > OFFLINE_DB_ID) {
            Settings.staticUserName = serverSetting.userName
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
     *
     * Null while no address is stored: a fresh install asks for one first (issue #192).
     */
    fun signInServer(): ServerSetting? = StaticServers.servers().firstOrNull()?.copy(
        userName = Settings.staticUserName
    )

    /**
     * The stored server address changed ([ServerAddress.store]): drops the cached server and
     * rebuilds the music service on the main thread, so the next request goes to the new address.
     */
    fun serverChanged() {
        invalidateCache()
        launch(Dispatchers.Main) { resetMusicService() }
    }

    /**
     * Records a session the Capacitor shell's web login just started -- with a password or with
     * Google -- so downloads, Android Auto and the rest of the native side see the same session:
     * the account's name, its MuMa API key (encrypted, [SecureSettings]; issue #115) and account id,
     * and the signed-in flag -- set only when the key could be stored. No password: the
     * page signed in with it and keeps no copy either, and nothing native needs it (issue #101).
     * The Subsonic token is fetched with the key afterwards
     * ([nl.teunschriks.mumamobile.service.SubsonicTokenRefresher]).
     *
     * A new session replaces whatever account was stored, id included (an [setMumaSettings] after
     * a login only fills an id that is missing). Under the sign-out epoch, like [signOut]: a token
     * fetch for the previous session that is still out must not store its answer afterwards.
     *
     * Written against [signInServer], not [getActiveServer]: on a fresh install the active server
     * is Offline, and the server is then made active as well, which is what the next boot's
     * `credentials()` relies on. Without a stored address there is no server to activate; the
     * shell never signs in before one is set.
     */
    fun saveSession(username: String, apiKey: String, userId: Int?) {
        val server = signInServer()
        SignOutEpoch.signOut {
            Settings.staticUserName = username
            val keyStored = SecureSettings.storeMumaApiKey(apiKey)
            Settings.clearLegacyMumaApiKey()
            Settings.mumaUserId = userId?.takeIf { isUsableMumaUserId(it) } ?: -1
            Settings.clearLegacyStaticPassword()
            Settings.signedIn = username.isNotEmpty() && apiKey.isNotEmpty() && keyStored
            invalidateCache()
        }
        launch(Dispatchers.Main) { resetMusicService() }
        if (server != null && getActiveServerId() == OFFLINE_DB_ID) setActiveServerById(server.id)
    }

    /**
     * Clears everything that can authenticate: the signed-in flag, any password an old build left
     * behind, the muma API key/user id and the encrypted muma and Subsonic tokens in
     * [SecureSettings]. The username is kept -- it is not a secret, and it is what the next
     * sign-in prefills. Callers that hold a [nl.teunschriks.mumamobile.service.MediaPlayerManager]
     * still have to clear its queue themselves -- that is not this class's job. Downloaded files
     * are untouched.
     */
    fun signOut() {
        clearSession()
        resetMusicService()
    }

    /**
     * MuMa refused [refusedKey] (HTTP 401): the key is permanent, so a refusal means the account's
     * key was revoked or the account is gone, and only a new sign-in helps (issue #101). Ends the
     * session like [signOut] does -- the shell then shows its sign-in page, and Android Auto
     * answers "sign in again in the MuMa app on your phone" -- but leaves the queue alone and
     * rebuilds the music service on the main thread, because this runs on the request's thread.
     *
     * Only when [refusedKey] is still the stored key: a sign-in that replaced it while the refused
     * request was out must not be undone by that request's answer. Returns whether it signed out.
     */
    fun keyRefused(refusedKey: String): Boolean {
        var cleared = false
        SignOutEpoch.signOut {
            if (refusedKey.isNotEmpty() && SecureSettings.mumaApiKey == refusedKey) {
                clearCredentials()
                cleared = true
            }
        }
        if (cleared) {
            Timber.w("MuMa refused the stored API key; signed out, sign in again")
            launch(Dispatchers.Main) { resetMusicService() }
        }
        return cleared
    }

    /** Clears the credentials under the sign-out epoch (bug reports 106 and 111). */
    private fun clearSession() {
        SignOutEpoch.signOut { clearCredentials() }
    }

    /** The clearing itself; the caller holds the sign-out epoch. */
    private fun clearCredentials() {
        Settings.signedIn = false
        Settings.clearLegacyStaticPassword()
        Settings.clearLegacyMumaApiKey()
        Settings.mumaUserId = -1
        SecureSettings.clear()
        invalidateCache()
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
     * Gets the Rest Url of the Active Server, without credentials.
     *
     * Its one caller, `CachedMusicService.checkSettingsChanged`, compares it to tell a server or
     * account switch; it is never requested. It used to carry the password as `p=enc:<hex>`, which
     * kept a reversible copy of it in a string that had no reason to hold one (bug report 103). A
     * different account still changes it through `u=`.
     *
     * @param method: The Rest resource to use
     * @return The Rest Url of the method on the server
     */
    fun getRestUrl(method: String?): String {
        val builder = StringBuilder(256)
        val activeServer = getActiveServer()
        builder.append(activeServer.url)
        if (builder.isEmpty() || builder[builder.length - 1] != '/') {
            builder.append('/')
        }
        builder.append("rest/").append(method).append(".view")
        builder.append("?u=").append(activeServer.userName)
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
         * Whether someone is signed in (issue #101): the explicit flag a sign-in sets and a
         * sign-out clears, for a stored name, and a MuMa API key that can still be read. The key
         * check is what turns a Keystore key that was lost or invalidated, or a backup restored
         * without the encrypted store, into "sign in again" (issue #115). Migrates an install that
         * still keeps a password or a plain key first ([migrateLegacyCredentials]), so a component
         * that starts before the app -- the media session Android Auto starts without the UI --
         * reads the same answer.
         */
        fun isSignedIn(): Boolean {
            migrateLegacyCredentials()
            return Settings.signedIn && Settings.staticUserName.isNotEmpty() && SecureSettings.mumaApiKey.isNotEmpty()
        }

        @Volatile
        private var legacyCredentialsChecked = false

        /**
         * Runs [LegacyPasswordMigration] and then [CredentialMigration] once per process. Called
         * from `UApp.onCreate` and from [isSignedIn], whichever comes first.
         */
        fun migrateLegacyCredentials() {
            if (legacyCredentialsChecked) return
            synchronized(this) {
                if (legacyCredentialsChecked) return
                if (LegacyPasswordMigration.run(SettingsPasswordStore)) {
                    Timber.i("Removed the stored password; signed in: %s", Settings.signedIn)
                }
                if (CredentialMigration.run(SettingsCredentialStore)) {
                    Timber.i("Moved the MuMa key into encrypted storage; signed in: %s", Settings.signedIn)
                }
                legacyCredentialsChecked = true
            }
        }

        /** Resets the once-per-process guard of [migrateLegacyCredentials]; tests only. */
        internal fun resetLegacyCredentialsCheck() {
            legacyCredentialsChecked = false
        }

        /** [CredentialMigration.Store] over [Settings] and [SecureSettings]. */
        private object SettingsCredentialStore : CredentialMigration.Store {
            override val plainApiKey: String get() = Settings.legacyMumaApiKey
            override fun clearPlainApiKey() = Settings.clearLegacyMumaApiKey()
            override fun storeEncryptedApiKey(key: String): Boolean = SecureSettings.storeMumaApiKey(key)
            override fun legacyEncryptedFileExists(): Boolean = SecureSettings.legacyFileExists()
            override fun deleteLegacyEncryptedFile() = SecureSettings.deleteLegacyFile()
            override var signedIn: Boolean
                get() = Settings.signedIn
                set(value) {
                    Settings.signedIn = value
                }
        }

        /** [LegacyPasswordMigration.Store] over [Settings]. */
        private object SettingsPasswordStore : LegacyPasswordMigration.Store {
            override val userName: String get() = Settings.staticUserName
            override val legacyPassword: String get() = Settings.legacyStaticPassword
            override fun clearLegacyPassword() = Settings.clearLegacyStaticPassword()
            override var signedIn: Boolean
                get() = Settings.signedIn
                set(value) {
                    Settings.signedIn = value
                }
        }

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
         * Queries if ID3 tags should be used.
         *
         * Hardcoded: the `id3_tags`/`id3_tags_offline` preferences that used to gate this are
         * retired (see docs/designs/universal-ui/functional.md, "Device settings"). ID3 mode picks
         * the endpoints in RESTMusicService, MediaLibraryBrowser/MediaLibraryDataProvider,
         * DownloadUtil and the *ListModel classes; those false branches are left in place rather
         * than deleted; they are simply unreachable now.
         */
        // Kept as a function, not a const val: every call site below uses shouldUseId3Tags()
        // rather than a property, and there are too many of them to be worth changing for this.
        @Suppress("FunctionOnlyReturningConstant")
        fun shouldUseId3Tags(): Boolean = true
    }
}
