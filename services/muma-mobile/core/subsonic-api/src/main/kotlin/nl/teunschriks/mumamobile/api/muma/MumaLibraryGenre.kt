/*
 * MumaLibraryGenre.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.muma

/**
 * One row of `/api/library/genres`.
 *
 * The genre names themselves come from Subsonic; this list is read for one field, `tint`. MuMa
 * derives that colour so the web UI and this app draw a genre in the same one, which is exactly
 * what a table on each side would fail to guarantee.
 *
 * `tint` is nullable because a server older than the field answers without it.
 */
data class MumaLibraryGenre(
    val genre: String = "",
    val state: String? = null,
    val count: Int = 0,
    val tint: String? = null
)
