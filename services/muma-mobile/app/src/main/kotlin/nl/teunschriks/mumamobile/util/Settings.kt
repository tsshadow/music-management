/*
 * Settings.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import androidx.preference.PreferenceManager
import java.util.regex.Pattern
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.home.HomeLimits

/**
 * Contains convenience functions for reading and writing preferences
 */
object Settings {

    @JvmStatic
    val preferences: SharedPreferences
        get() = PreferenceManager.getDefaultSharedPreferences(Util.appContext())

    // Which launcher icon is showing. The icon lives in the manifest and is switched by enabling
    // one activity-alias; nothing writes this any more since the Kotlin settings screen went, so
    // an install keeps whichever colour it picked and a fresh one gets green.
    @JvmStatic
    var appIcon by StringSetting(
        getKey(R.string.setting_key_app_icon),
        getKey(R.string.setting_key_app_icon_green)
    )

    @JvmStatic
    var isSetsMode by BooleanSetting(
        getKey(R.string.setting_key_is_sets_mode),
        false
    )

    // One row per song instead of one per file: the server keeps the version MuMa named best
    // and leaves out the other copies. On by default, matching the web player. What it hides
    // stays reachable through the Versions list in the track info sheet -- that list is why
    // this may default to on at all.
    @JvmStatic
    var canonicalOnly by BooleanSetting(
        getKey(R.string.setting_key_canonical_only),
        true
    )

    // The memories carousel on the home screen. Only the teaser: the Memories page in the Library
    // tab stays reachable whatever this is set to.
    @JvmStatic
    var memoriesOnHome by BooleanSetting(
        getKey(R.string.setting_key_memories_on_home),
        true
    )

    // When on, the home screen keeps one shortcut history for songs and another for livesets.
    @JvmStatic
    var separateHomeHistoryPerMode by BooleanSetting(
        getKey(R.string.setting_key_separate_home_history),
        true
    )

    // How many shortcuts the "Recently played" grid shows. Read through HomeLimits.shortcuts(),
    // which is what turns an unwritten key or a hand-edited value into something renderable.
    @JvmStatic
    var homeShortcutCount
        by StringIntSetting(
            getKey(R.string.setting_key_home_shortcut_count),
            HomeLimits.DEFAULT_SHORTCUTS
        )

    // Rows per home track list, before "Show more". Read through HomeLimits.listRows().
    @JvmStatic
    var homeListCount
        by StringIntSetting(
            getKey(R.string.setting_key_home_list_count),
            HomeLimits.DEFAULT_LIST_ROWS
        )

    /** The live stations the listener marked in the web layer. The car lists them first. */
    var favoriteStations by StringSetting("favorite_stations", "")

    // One mode per home section. Stored as the HomeSectionMode name; everything that reads them
    // goes through HomeLayoutSettings, which is what turns an unwritten or hand-edited value into
    // something renderable. Memories' old on/off checkbox is still read as a fallback there.
    @JvmStatic
    var homeModeMemories by StringSetting(getKey(R.string.setting_key_home_mode_memories), "")

    @JvmStatic
    var homeModeReleaseRadar by StringSetting(getKey(R.string.setting_key_home_mode_release_radar), "")

    @JvmStatic
    var homeModeDailyMix by StringSetting(getKey(R.string.setting_key_home_mode_daily_mix), "")

    @JvmStatic
    var homeModeFavorites by StringSetting(getKey(R.string.setting_key_home_mode_favorites), "")

    @JvmStatic
    var homeModeShortcuts by StringSetting(getKey(R.string.setting_key_home_mode_shortcuts), "")

    @JvmStatic
    var homeModeRecentlyReleased by StringSetting(getKey(R.string.setting_key_home_mode_recently_released), "")

    @JvmStatic
    var homeModeRecentlyAdded by StringSetting(getKey(R.string.setting_key_home_mode_recently_added), "")

    // The two sections that are new enough not to have a count of their own yet. Shortcuts and the
    // recent lists keep reading home_shortcut_count and home_list_count, so an upgrade shows the
    // same amount of the same things it showed yesterday.
    @JvmStatic
    var homeCountDailyMix by StringIntSetting(getKey(R.string.setting_key_home_count_daily_mix), 0)

    @JvmStatic
    var homeCountFavorites by StringIntSetting(getKey(R.string.setting_key_home_count_favorites), 0)

    @JvmStatic
    var lastSyncedVersion by IntSetting(
        getKey(R.string.setting_key_last_synced_version),
        0
    )

    @JvmStatic
    val maxBitRate: Int
        get() {
            return if (Util.isNetworkRestricted()) {
                maxBitRateMobile
            } else {
                maxBitRateWifi
            }
        }

    // Not private: MumaSystemPlugin's device-settings whitelist reads and writes both directly,
    // rather than through maxBitRate, which only ever answers for the network the phone is on.
    @JvmStatic
    var maxBitRateWifi
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_wifi))

    @JvmStatic
    var maxBitRateMobile
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_mobile))

    @JvmStatic
    var maxBitRatePinning
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_pinning))
    val pinWithHighestQuality: Boolean
        get() = (maxBitRatePinning == 0)

    // Not private, for the same reason as maxBitRateWifi/maxBitRateMobile above: the
    // device-settings whitelist reads and writes it directly.
    @JvmStatic
    var networkTimeout by StringIntSetting(getKey(R.string.setting_key_network_timeout), 60000)

    @JvmStatic
    val preloadCount: Int
        get() {
            val preloadCount =
                preferences.getString(getKey(R.string.setting_key_preload_count), "-1")!!
                    .toInt()
            return if (preloadCount == -1) Int.MAX_VALUE else preloadCount
        }

    /**
     * Writes the raw preference behind [preloadCount]. `-1` is the sentinel [preloadCount] turns
     * into "no limit" on read; this is what the device-settings whitelist writes with, so it takes
     * the same sentinel rather than [Int.MAX_VALUE] a caller would otherwise have to know about.
     */
    @JvmStatic
    fun setPreloadCount(count: Int) {
        preferences.edit { putString(getKey(R.string.setting_key_preload_count), count.toString()) }
    }

    @JvmStatic
    var parallelDownloads by IntSetting(getKey(R.string.setting_key_parallel_downloads), 3)

    @JvmStatic
    val cacheSizeMB: Int
        get() {
            val cacheSize = preferences.getString(
                getKey(R.string.setting_key_cache_size),
                "-1"
            )!!.toInt()
            return if (cacheSize == -1) Int.MAX_VALUE else cacheSize
        }

    /** Writes the raw preference behind [cacheSizeMB]; see [setPreloadCount] for the `-1` sentinel. */
    @JvmStatic
    fun setCacheSizeMB(sizeMB: Int) {
        preferences.edit { putString(getKey(R.string.setting_key_cache_size), sizeMB.toString()) }
    }

    @JvmStatic
    var customCacheLocation by BooleanSetting(
        getKey(R.string.setting_key_custom_cache_location),
        false
    )

    @JvmStatic
    var cacheLocationUri by StringSetting(
        getKey(R.string.setting_key_cache_location),
        ""
    )

    @JvmStatic
    var isWifiRequiredForDownload by BooleanSetting(
        getKey(R.string.setting_key_wifi_required_for_download),
        false
    )

    @JvmStatic
    var autoSwitchOffline by BooleanSetting(
        getKey(R.string.setting_key_auto_switch_offline),
        false
    )

    // The .nomedia marker itself is HideMediaEffect's job, not this property's; both
    // SettingsFragment and MumaSystem.setSetting's "hideMedia" entry call that after writing this.
    @JvmStatic
    var hideMedia by BooleanSetting(
        getKey(R.string.setting_key_hide_media),
        false
    )

    // Retired from the settings screen; the Shares fragment is dead code but still writes this, so
    // it stays a plain in-memory var instead of a val.
    @JvmStatic
    var shareOnServer = true

    @JvmStatic
    var shouldDisplayBitrateWithArtist by BooleanSetting(
        getKey(R.string.setting_key_display_bitrate_with_artist),
        true
    )

    // Retired from the settings screen; AlbumHeader still branches on it, so the value is frozen
    // at the default rather than deleted outright.
    @JvmStatic
    val shouldUseFolderForArtistName = false

    @JvmStatic
    var shouldShowTrackNumber
        by BooleanSetting(getKey(R.string.setting_key_show_track_number), false)

    /**
     * How many lines a track row uses. Two keeps the compact row; three splits album and artist
     * onto their own lines and moves rating, release date and duration to the right.
     */
    @JvmStatic
    var trackListLines by StringIntSetting(
        getKey(R.string.setting_key_track_list_lines),
        TRACK_LIST_LINES_COMPACT
    )

    // default_artists/albums/songs and max_artists/albums/songs used to be a settings screen of
    // their own; the web player enforces its own search limits, so the legacy Kotlin UI keeps
    // reading these exact numbers -- the values res/xml/settings.xml shipped as defaults -- with
    // no row left anywhere to change them.
    @JvmStatic
    val defaultAlbums = 5

    @JvmStatic
    val maxAlbums = 20

    @JvmStatic
    val defaultSongs = 10

    @JvmStatic
    val maxSongs = 500

    @JvmStatic
    val maxArtists = 10

    @JvmStatic
    val defaultArtists = 3

    // Bookmarks are replaced by set resume; skip is a fixed +/-30s rather than a configurable
    // increment_time preference.
    @JvmStatic
    val seekInterval = 30000

    val seekIntervalMillis: Long
        get() = (seekInterval / 1000).toLong()

    var resumePlayOnHeadphonePlug
        by BooleanSetting(R.string.setting_key_resume_play_on_headphones_plug, true)

    @JvmStatic
    var resumeOnBluetoothDevice by IntSetting(
        getKey(R.string.setting_key_resume_on_bluetooth_device),
        Constants.PREFERENCE_VALUE_DISABLED
    )

    @JvmStatic
    var pauseOnBluetoothDevice by IntSetting(
        getKey(R.string.setting_key_pause_on_bluetooth_device),
        Constants.PREFERENCE_VALUE_A2DP
    )

    /** The manual "I am in the car" switch, one of the three inputs to CarPresence. */
    @JvmStatic
    var carModeManual by BooleanSetting(
        getKey(R.string.setting_key_car_mode_manual),
        false
    )

    /**
     * Bluetooth addresses the user has marked as their car.
     *
     * Deliberately a stored choice rather than a device-class check: plenty of car kits report
     * neither AUDIO_VIDEO_CAR_AUDIO nor AUDIO_VIDEO_HANDSFREE, and some headsets report the second.
     * Guessing is how earbuds start car mode.
     */
    @JvmStatic
    var carModeDevices by StringSetSetting(
        getKey(R.string.setting_key_car_mode_devices),
        emptySet()
    )

    /** Set once the user has seen the device list, so an empty choice is not re-filled. */
    @JvmStatic
    var carModeDevicesChosen by BooleanSetting(
        getKey(R.string.setting_key_car_mode_devices_chosen),
        false
    )

    // The media3 notification is mandatory for a foreground service; this toggle never actually
    // gated it. Retired from the settings screen, frozen at the default it always effectively had.
    @JvmStatic
    val showNowPlaying = true

    @JvmStatic
    val showNowPlayingDetails = true

    var scrobbleEnabled by BooleanSetting(getKey(R.string.setting_key_scrobble), true)

    // Normally you don't need to use these Settings directly,
    // use ActiveServerProvider.isID3Enabled() instead
    //
    // Retired from the settings screen: ActiveServerProvider.shouldUseId3Tags() is hardcoded to
    // true and no longer reads either of these. They stay plain in-memory vars, defaulting true,
    // rather than vals, only because a few unit tests still poke them directly to exercise the
    // handful of call sites that read the property instead of the function.
    @JvmStatic
    var id3TagsEnabledOnline = true

    // See comment above.
    @JvmStatic
    var id3TagsEnabledOffline = true

    var activeServer by IntSetting(getKey(R.string.setting_key_server_instance), -1)

    var firstRunExecuted by BooleanSetting(getKey(R.string.setting_key_first_run_executed), false)

    /**
     * Whether the one-time push of this account's Subsonic bookmarks into the
     * `setResume` account-settings key (the web's set-resume feature) has
     * already run. See `BookmarkMigration.kt` -- this exists so a listener's
     * bookmarks are not re-pushed, and any resume position they have since
     * moved past on another device is not clobbered, on every later launch.
     */
    var bookmarksMigratedToSetResume
        by BooleanSetting(getKey(R.string.setting_key_bookmarks_migrated_to_set_resume), false)

    // In-memory rather than persisted: ArtistHeaderBinderTest/ArtistRowBinderTest flip this to
    // isolate themselves from the real Koin-backed image loader; there is otherwise no settings
    // screen row, and no persistence, left for it.
    @JvmStatic
    var shouldShowArtistPicture = true

    // Shares/Chat fragments are dead code; every setting below this point that only fed one of
    // them is frozen at its default rather than deleted, since these are still real properties a
    // handful of call sites in those fragments read.
    @JvmStatic
    val chatRefreshInterval = 5000

    var directoryCacheTime by StringIntSetting(
        getKey(R.string.setting_key_directory_cache_time),
        300
    )

    var shouldSortByDisc
        by BooleanSetting(getKey(R.string.setting_key_disc_sort), false)

    // Bookmarks are replaced by set resume.
    // Not a const val: ktlint wants SCREAMING_SNAKE_CASE for those, and renaming would touch
    // every call site that still reads this camelCase property name.
    @Suppress("MayBeConst")
    val shouldClearBookmark = false

    // In-memory rather than persisted: the Shares fragment that writes this is dead code, but it
    // still compiles and still writes, so this stays a plain var instead of a val.
    var shouldAskForShareDetails = true

    var defaultShareDescription = ""

    @JvmStatic
    val shareGreeting: String?
        get() {
            val context = Util.appContext()
            return String.format(
                context.resources.getString(R.string.share_default_greeting),
                context.resources.getString(R.string.common_appname)
            )
        }

    var defaultShareExpiration = "0"

    // TimeSpanPicker.calculateTimeSpan needs a live Context to resolve a "weeks"/"months" span,
    // which is why this used to be computed instead of frozen; the Shares fragment that read it is
    // dead code, so a fixed "no expiration" answer costs nothing.
    @Suppress("MayBeConst")
    val defaultShareExpirationInMillis: Long = 0

    @JvmStatic
    var debugLogToFile by BooleanSetting(
        getKey(R.string.setting_key_debug_log_to_file),
        BuildConfig.DEBUG
    )

    /**
     * Off by default in every build type: the detection infers a crash from a missing clean
     * shutdown, and Android silently kills the process often enough that leaving it on would
     * nag about a "crash" after most ordinary app exits.
     */
    @JvmStatic
    var crashDetectionEnabled by BooleanSetting(
        getKey(R.string.setting_key_crash_detection),
        false
    )

    // Was a val: only the legacy ListPreference wrote it, straight to SharedPreferences, never
    // through this property. MumaSystemPlugin.setAppLocale writes it through the property instead,
    // so it has to be a var now -- see docs/designs/universal-ui/functional.md, "Device settings".
    @JvmStatic
    var overrideLanguage by StringSetting(getKey(R.string.setting_key_override_language), "")

    var useHwOffload by BooleanSetting(getKey(R.string.setting_key_hardware_offload), false)

    @JvmStatic
    var firstInstalledVersion by IntSetting(
        getKey(R.string.setting_key_first_installed_version),
        0
    )

    @JvmStatic
    var showConfirmationDialog by BooleanSetting(
        getKey(R.string.setting_key_show_confirmation_dialog),
        false
    )

    @JvmStatic
    var lastViewType by IntSetting(
        getKey(R.string.setting_key_last_view_type),
        0
    )

    @JvmStatic
    var lastSeenVersion by IntSetting(
        getKey(R.string.setting_key_last_seen_version),
        0
    )

    /**
     * The MuMa API key builds before issue #115 kept here in plain text. Nothing writes it any
     * more: the key lives encrypted in [SecureSettings.mumaApiKey], and
     * [nl.teunschriks.mumamobile.data.CredentialMigration] moves this copy there once and removes
     * it with [clearLegacyMumaApiKey].
     */
    @JvmStatic
    val legacyMumaApiKey: String
        get() = preferences.getString(getKey(R.string.setting_key_muma_api_key), null) ?: ""

    /** Removes the key [legacyMumaApiKey] reads, rather than leaving it behind blank. */
    fun clearLegacyMumaApiKey() {
        preferences.edit(commit = true) { remove(getKey(R.string.setting_key_muma_api_key)) }
    }

    @JvmStatic
    var mumaUserId by StringIntSetting(getKey(R.string.setting_key_muma_user_id), -1)

    // Settings offers this as a ListPreference, which stores its value as a String, so this has to
    // be a StringIntSetting under that same key - an IntSetting under a key of its own meant the
    // preference wrote a value nothing ever read.
    @JvmStatic
    var genreTrackLimit
        by StringIntSetting(getKey(R.string.setting_key_genre_track_limit), 100)

    // Written by PlayHistoryRecorder on every scrobble, read by the Android Auto browser.
    @JvmStatic
    var lastPlayedGenres by StringSetting("last_played_genres", "[]")

    @JvmStatic
    var lastPlayedLiveGenres by StringSetting("last_played_live_genres", "[]")

    @JvmStatic
    var lastSelectedGenres by StringSetting("last_selected_genres", "[]")

    @JvmStatic
    var lastSelectedLiveGenres by StringSetting("last_selected_live_genres", "[]")

    // Local copy of the list the web player keeps in the MuMa "frontend" settings blob.
    @JvmStatic
    var favoriteGenres by StringSetting("favorite_genres", "[]")

    @JvmStatic
    var mediaDeviceExportEnabled by BooleanSetting(
        getKey(R.string.setting_key_media_device_export),
        false
    )

    @JvmStatic
    var staticUserName by StringSetting(getKey(R.string.setting_key_static_username), "")

    /**
     * The server address the listener chose on the first-run screen, normalized; `""` while none
     * is set (issue #192). Read and written through [nl.teunschriks.mumamobile.data.ServerAddress]
     * only. Not a secret: it stays in the cloud backup with the other plain preferences.
     */
    @JvmStatic
    var serverUrl by StringSetting(getKey(R.string.setting_key_server_url), "")

    /**
     * Whether someone is signed in: set by a sign-in ([nl.teunschriks.mumamobile.data.ActiveServerProvider.saveSession]),
     * cleared by a sign-out. Replaces the blank password that used to mean "signed out" (issue
     * #101); read it through [nl.teunschriks.mumamobile.data.ActiveServerProvider.isSignedIn],
     * which first migrates an install that still has a password stored.
     */
    @JvmStatic
    var signedIn by BooleanSetting(getKey(R.string.setting_key_signed_in), false)

    /**
     * The password builds before issue #101 kept here in plain text after a sign-in. Nothing
     * writes it any more; [nl.teunschriks.mumamobile.data.LegacyPasswordMigration] reads it once
     * to decide [signedIn] and then removes it with [clearLegacyStaticPassword].
     */
    @JvmStatic
    val legacyStaticPassword: String
        get() = preferences.getString(getKey(R.string.setting_key_static_password), null) ?: ""

    /** Removes the key [legacyStaticPassword] reads, rather than leaving it behind blank. */
    fun clearLegacyStaticPassword() {
        preferences.edit { remove(getKey(R.string.setting_key_static_password)) }
    }

    fun hasKey(key: String): Boolean = preferences.contains(key)

    private fun getKey(key: Int): String = appContext.getString(key)

    fun getAllKeys(): List<String> = preferences.all.keys.toList()

    private val appContext: Context
        get() = UApp.applicationContext()

    val COLON_PATTERN: Pattern = Pattern.compile(":")

    const val TRACK_LIST_LINES_COMPACT = 2
    const val TRACK_LIST_LINES_DETAILED = 3
}
