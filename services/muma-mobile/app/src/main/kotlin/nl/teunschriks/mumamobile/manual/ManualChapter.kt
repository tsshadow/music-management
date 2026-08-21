/*
 * ManualChapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.manual

import androidx.annotation.DrawableRes
import androidx.annotation.IdRes
import androidx.annotation.StringRes
import nl.teunschriks.mumamobile.R

/**
 * One chapter of the in-app manual.
 *
 * The body is an HTML string resource rather than plain text, because a manual without emphasis
 * and line breaks reads as a wall. It is rendered through HtmlCompat, so the markup in
 * `strings.xml` is what the reader sees.
 *
 * [screenshot] points at a picture in `res/drawable-nodpi`. Those ship as placeholders on
 * purpose: the layout, the sizing and the tap-to-enlarge all work before a single real
 * screenshot exists, and replacing one is dropping a PNG over the placeholder of the same name.
 * See `docs/manual-screenshots.md`.
 *
 * [actionLabel] and [actionDestination] give a chapter a way out to the screen it describes,
 * for the chapters where reading about it is the slower way to learn it.
 */
data class ManualChapter(
    @StringRes val title: Int,
    @StringRes val body: Int,
    @DrawableRes val icon: Int,
    @DrawableRes val screenshot: Int?,
    @StringRes val actionLabel: Int? = null,
    @IdRes val actionDestination: Int? = null
)

/**
 * The manual itself, in reading order: what you set up first, then what you look at most, then
 * the parts you only need once something is wrong.
 */
val manualChapters: List<ManualChapter> = listOf(
    ManualChapter(
        title = R.string.manual_chapter_start_title,
        body = R.string.manual_chapter_start_body,
        icon = R.drawable.ic_menu_server,
        screenshot = R.drawable.manual_start,
        actionLabel = R.string.manual_action_servers,
        actionDestination = R.id.serverSelectorFragment
    ),
    ManualChapter(
        title = R.string.manual_chapter_home_title,
        body = R.string.manual_chapter_home_body,
        icon = R.drawable.ic_menu_browse,
        screenshot = R.drawable.manual_home
    ),
    ManualChapter(
        title = R.string.manual_chapter_library_title,
        body = R.string.manual_chapter_library_body,
        icon = R.drawable.ic_menu_playlists,
        screenshot = R.drawable.manual_library
    ),
    ManualChapter(
        title = R.string.manual_chapter_favorites_title,
        body = R.string.manual_chapter_favorites_body,
        icon = R.drawable.ic_star_full,
        screenshot = R.drawable.manual_favorites
    ),
    ManualChapter(
        title = R.string.manual_chapter_search_title,
        body = R.string.manual_chapter_search_body,
        icon = R.drawable.ic_menu_search,
        screenshot = R.drawable.manual_search
    ),
    ManualChapter(
        title = R.string.manual_chapter_player_title,
        body = R.string.manual_chapter_player_body,
        icon = R.drawable.baseline_music_note_24,
        screenshot = R.drawable.manual_player
    ),
    ManualChapter(
        title = R.string.manual_chapter_voice_title,
        body = R.string.manual_chapter_voice_body,
        icon = R.drawable.ic_menu_microphone,
        screenshot = R.drawable.manual_voice,
        actionLabel = R.string.manual_action_voice_commands,
        actionDestination = R.id.voiceCommandsFragment
    ),
    ManualChapter(
        title = R.string.manual_chapter_car_title,
        body = R.string.manual_chapter_car_body,
        icon = R.drawable.ic_manual_car,
        screenshot = R.drawable.manual_car
    ),
    ManualChapter(
        title = R.string.manual_chapter_offline_title,
        body = R.string.manual_chapter_offline_body,
        icon = R.drawable.ic_menu_download,
        screenshot = R.drawable.manual_offline,
        actionLabel = R.string.manual_action_downloads,
        actionDestination = R.id.downloadsFragment
    ),
    ManualChapter(
        title = R.string.manual_chapter_settings_title,
        body = R.string.manual_chapter_settings_body,
        icon = R.drawable.ic_menu_settings,
        screenshot = R.drawable.manual_settings,
        actionLabel = R.string.manual_action_settings,
        actionDestination = R.id.settingsFragment
    ),
    ManualChapter(
        title = R.string.manual_chapter_update_title,
        body = R.string.manual_chapter_update_body,
        icon = R.drawable.ic_menu_refresh,
        screenshot = R.drawable.manual_update,
        actionLabel = R.string.manual_action_about,
        actionDestination = R.id.aboutFragment
    ),
    ManualChapter(
        title = R.string.manual_chapter_trouble_title,
        body = R.string.manual_chapter_trouble_body,
        icon = R.drawable.ic_baseline_info,
        screenshot = R.drawable.manual_trouble,
        actionLabel = R.string.manual_action_diagnostics,
        actionDestination = R.id.voiceDiagnosticsFragment
    )
)
