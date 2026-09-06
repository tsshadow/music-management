/*
 * ManagementPage.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import nl.teunschriks.mumamobile.R

/**
 * How the management pages are grouped, mirroring `MANAGEMENT_GROUPS` in
 * `services/frontend/src/lib/router.js`.
 *
 * A group whose [titleRes] is null is what the web calls a standalone entry: it holds exactly one
 * page and renders as a single row rather than a header with rows under it, because a group of one
 * only adds a line to read.
 */
enum class ManagementGroup(val id: String, val titleRes: Int?) {
    OVERVIEW("overview", null),
    COLLECTION("collection", R.string.management_group_collection),
    CURATION("curation", R.string.management_group_curation),
    DOWNLOADERS("downloaders", null),
    CHANNELS("channels", R.string.management_group_channels),
    ACCESS("access", R.string.management_group_access),
    SYSTEM("system", R.string.management_group_system),
    SETTINGS("settings", R.string.management_group_settings)
}

/**
 * Every page the management section has, in the order the web sidebar lists them.
 *
 * This enum *is* the mirror of the web's `MANAGEMENT_GROUPS`: same [id]s, same order, same groups.
 * `ManagementPageTest` is what keeps the two codebases from drifting apart, and the [id] is the
 * thing it compares — it is the web's tab id, which is also its `/management/<id>` route.
 *
 * [isBuilt] says whether the page exists in the app yet. The ones that do not are still listed, and
 * shown disabled: the index is then the honest picture of what management contains, and a later
 * batch lights a row up rather than adding one.
 *
 * There is deliberately no per-page permission here. The web sidebar hides a handful of pages
 * behind permissions it reads from its session; the app has no permission set of its own, gates the
 * whole Beheer tab on [ManagementRepository.isAdmin], and leaves the real boundary where it belongs,
 * on the server.
 */
enum class ManagementPage(
    val id: String,
    val titleRes: Int,
    val group: ManagementGroup,
    val isBuilt: Boolean = false
) {
    OVERVIEW("overview", R.string.management_tab_overview, ManagementGroup.OVERVIEW, isBuilt = true),
    LIBRARY("library", R.string.management_tab_library, ManagementGroup.COLLECTION),
    SCANNER("scanner", R.string.management_tab_scanner, ManagementGroup.COLLECTION),
    IMAGES("images", R.string.management_tab_images, ManagementGroup.COLLECTION),
    PLAYLISTS("playlists", R.string.management_tab_playlists, ManagementGroup.COLLECTION),
    TAGGER("tagger", R.string.management_tab_tagger, ManagementGroup.CURATION, isBuilt = true),
    GENRE_CURATION(
        "genre-curation",
        R.string.management_tab_genre_curation,
        ManagementGroup.CURATION,
        isBuilt = true
    ),
    LABEL_PROPOSALS(
        "label-proposals",
        R.string.management_tab_label_proposals,
        ManagementGroup.CURATION,
        isBuilt = true
    ),
    PODCAST_CURATION(
        "podcast-curation",
        R.string.management_tab_podcast_curation,
        ManagementGroup.CURATION,
        isBuilt = true
    ),
    DOWNLOADERS(
        "downloaders",
        R.string.management_tab_downloaders,
        ManagementGroup.DOWNLOADERS,
        isBuilt = true
    ),
    RADIO("radio", R.string.management_tab_radio, ManagementGroup.CHANNELS),
    NEWS("news", R.string.management_tab_news, ManagementGroup.CHANNELS),
    USERS("users", R.string.management_tab_users, ManagementGroup.ACCESS, isBuilt = true),
    USER_REQUESTS(
        "user-requests",
        R.string.management_tab_requests,
        ManagementGroup.ACCESS,
        isBuilt = true
    ),
    HEALTH("health", R.string.management_tab_health, ManagementGroup.SYSTEM, isBuilt = true),
    EVENTS("events", R.string.management_tab_events, ManagementGroup.SYSTEM, isBuilt = true),
    SCROBBLE("scrobble", R.string.management_tab_scrobble, ManagementGroup.SYSTEM),
    LIBRARIES("libraries", R.string.management_tab_libraries, ManagementGroup.SETTINGS),
    CONFIG("config", R.string.management_tab_config, ManagementGroup.SETTINGS)
}

/** One line of the management index: either a group header or a page to open. */
sealed interface ManagementIndexItem {

    /** The header above a group's pages. Only groups with a title get one. */
    data class Header(val group: ManagementGroup) : ManagementIndexItem

    /** A page, tappable when [ManagementPage.isBuilt]. */
    data class Row(val page: ManagementPage) : ManagementIndexItem
}

/**
 * The index in display order: each group's header, if it has one, followed by its pages.
 *
 * Pure, so the order can be asserted without inflating anything — Robolectric renders nothing here.
 */
fun managementIndexItems(
    pages: List<ManagementPage> = ManagementPage.entries
): List<ManagementIndexItem> = ManagementGroup.entries.flatMap { group ->
    val rows = pages.filter { it.group == group }.map { ManagementIndexItem.Row(it) }

    when {
        rows.isEmpty() -> emptyList()
        group.titleRes == null -> rows
        else -> listOf(ManagementIndexItem.Header(group)) + rows
    }
}
