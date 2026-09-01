/*
 * Settings.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import android.content.SharedPreferences
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

    @JvmStatic
    var style by StringSetting(
        getKey(R.string.setting_key_style),
        getKey(R.string.setting_key_style_spotify)
    )

    // Which launcher icon is showing. Deliberately independent of [accent]: the icon lives
    // in the manifest and is switched by enabling one activity-alias, not by the theme.
    @JvmStatic
    var appIcon by StringSetting(
        getKey(R.string.setting_key_app_icon),
        getKey(R.string.setting_key_app_icon_green)
    )

    /**
     * Percentage the whole interface is scaled by. 100 is the density the device reports,
     * lower values shrink every dp and sp so more content fits on screen.
     */
    @JvmStatic
    var uiScalePercent by StringIntSetting(
        getKey(R.string.setting_key_ui_scale),
        DEFAULT_UI_SCALE_PERCENT
    )

    @JvmStatic
    var isSetsMode by BooleanSetting(
        getKey(R.string.setting_key_is_sets_mode),
        false
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

    private var maxBitRateWifi
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_wifi))

    private var maxBitRateMobile
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_mobile))

    var maxBitRatePinning
        by StringIntSetting(getKey(R.string.setting_key_max_bitrate_pinning))
    val pinWithHighestQuality: Boolean
        get() = (maxBitRatePinning == 0)

    @JvmStatic
    val preloadCount: Int
        get() {
            val preloadCount =
                preferences.getString(getKey(R.string.setting_key_preload_count), "-1")!!
                    .toInt()
            return if (preloadCount == -1) Int.MAX_VALUE else preloadCount
        }

    val parallelDownloads by IntSetting(getKey(R.string.setting_key_parallel_downloads), 3)

    @JvmStatic
    val cacheSizeMB: Int
        get() {
            val cacheSize = preferences.getString(
                getKey(R.string.setting_key_cache_size),
                "-1"
            )!!.toInt()
            return if (cacheSize == -1) Int.MAX_VALUE else cacheSize
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

    @JvmStatic
    var shareOnServer by BooleanSetting(getKey(R.string.setting_key_share_on_server), true)

    @JvmStatic
    var shouldDisplayBitrateWithArtist by BooleanSetting(
        getKey(R.string.setting_key_display_bitrate_with_artist),
        true
    )

    @JvmStatic
    var shouldUseFolderForArtistName
        by BooleanSetting(getKey(R.string.setting_key_use_folder_for_album_artist), false)

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

    @JvmStatic
    var defaultAlbums
        by StringIntSetting(getKey(R.string.setting_key_default_albums), 5)

    @JvmStatic
    var maxAlbums
        by StringIntSetting(getKey(R.string.setting_key_max_albums), 20)

    @JvmStatic
    var defaultSongs
        by StringIntSetting(getKey(R.string.setting_key_default_songs), 10)

    @JvmStatic
    var maxSongs
        by StringIntSetting(getKey(R.string.setting_key_max_songs), 25)

    @JvmStatic
    var maxArtists
        by StringIntSetting(getKey(R.string.setting_key_max_artists), 10)

    @JvmStatic
    var defaultArtists
        by StringIntSetting(getKey(R.string.setting_key_default_artists), 3)

    @JvmStatic
    var seekInterval
        by StringIntSetting(getKey(R.string.setting_key_increment_time), 5000)

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

    @JvmStatic
    var showNowPlaying
        by BooleanSetting(getKey(R.string.setting_key_show_now_playing), true)

    @JvmStatic
    var shouldTransitionOnPlayback by BooleanSetting(
        getKey(R.string.setting_key_download_transition),
        true
    )

    @JvmStatic
    var showNowPlayingDetails
        by BooleanSetting(getKey(R.string.setting_key_show_now_playing_details), false)

    var scrobbleEnabled by BooleanSetting(getKey(R.string.setting_key_scrobble), true)

    // Normally you don't need to use these Settings directly,
    // use ActiveServerProvider.isID3Enabled() instead
    @JvmStatic
    var id3TagsEnabledOnline by BooleanSetting(getKey(R.string.setting_key_id3_tags), true)

    // See comment above.
    @JvmStatic
    var id3TagsEnabledOffline by BooleanSetting(getKey(R.string.setting_key_id3_tags_offline), true)

    var activeServer by IntSetting(getKey(R.string.setting_key_server_instance), -1)

    var serverScaling by BooleanSetting(getKey(R.string.setting_key_server_scaling), false)

    var firstRunExecuted by BooleanSetting(getKey(R.string.setting_key_first_run_executed), false)

    val shouldShowArtistPicture
        by BooleanSetting(getKey(R.string.setting_key_show_artist_picture), true)

    @JvmStatic
    var chatRefreshInterval by StringIntSetting(
        getKey(R.string.setting_key_chat_refresh_interval),
        5000
    )

    var directoryCacheTime by StringIntSetting(
        getKey(R.string.setting_key_directory_cache_time),
        300
    )

    var shouldSortByDisc
        by BooleanSetting(getKey(R.string.setting_key_disc_sort), false)

    var shouldClearBookmark
        by BooleanSetting(getKey(R.string.setting_key_clear_bookmark), false)

    var shouldAskForShareDetails
        by BooleanSetting(getKey(R.string.setting_key_ask_for_share_details), true)

    var defaultShareDescription
        by StringSetting(getKey(R.string.setting_key_default_share_description), "")

    @JvmStatic
    val shareGreeting: String?
        get() {
            val context = Util.appContext()
            val defaultVal = String.format(
                context.resources.getString(R.string.share_default_greeting),
                context.resources.getString(R.string.common_appname)
            )
            return preferences.getString(
                getKey(R.string.setting_key_default_share_greeting),
                defaultVal
            )
        }

    var defaultShareExpiration by StringSetting(
        getKey(R.string.setting_key_default_share_expiration),
        "0"
    )

    val defaultShareExpirationInMillis: Long
        get() {
            val preference = defaultShareExpiration
            val split = COLON_PATTERN.split(preference)
            if (split.size == 2) {
                val timeSpanAmount = split[0].toLong()
                val timeSpanType = split[1]
                return TimeSpanPicker.calculateTimeSpan(appContext, timeSpanType, timeSpanAmount)
            }
            return 0
        }

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

    @JvmStatic
    val overrideLanguage by StringSetting(getKey(R.string.setting_key_override_language), "")

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

    @JvmStatic
    var mumaApiKey by StringSetting(getKey(R.string.setting_key_muma_api_key), "")

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

    @JvmStatic
    var staticPassword by StringSetting(getKey(R.string.setting_key_static_password), "")

    fun hasKey(key: String): Boolean = preferences.contains(key)

    private fun getKey(key: Int): String = appContext.getString(key)

    fun getAllKeys(): List<String> = preferences.all.keys.toList()

    private val appContext: Context
        get() = UApp.applicationContext()

    val COLON_PATTERN: Pattern = Pattern.compile(":")

    const val DEFAULT_UI_SCALE_PERCENT = 75

    const val TRACK_LIST_LINES_COMPACT = 2
    const val TRACK_LIST_LINES_DETAILED = 3
}
