/*
 * BrowseArtwork.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.net.Uri
import androidx.annotation.ColorInt
import nl.teunschriks.mumamobile.provider.AlbumArtContentProvider
import nl.teunschriks.mumamobile.provider.GeneratedArtContentProvider
import nl.teunschriks.mumamobile.util.FileUtil

/**
 * Which picture a browsable entry in the car gets.
 *
 * A real photo always wins. The drawn cover exists for the entries that have none -- and those are
 * what keep a level a text list, because Android Auto only lays a level out as a grid when its
 * entries have something to show.
 */
object BrowseArtwork {

    /** A genre never has a picture of its own, so it is always drawn. */
    fun forGenre(name: String, @ColorInt tint: Int): Uri? = GeneratedArtContentProvider.artUri(PlaylistArtKind.GENRE, name, tint)

    /**
     * The artist's portrait when MuMa has one, initials on the genre's colour otherwise.
     *
     * A blank cover-art id counts as none: the server sends an empty string rather than omitting
     * the field, and an empty id resolves to no picture at all.
     */
    fun forArtist(coverArt: String?, name: String?, @ColorInt tint: Int): Uri? {
        if (!coverArt.isNullOrBlank()) {
            val portrait = AlbumArtContentProvider.mapArtworkToContentProviderUri(
                coverArt,
                FileUtil.getArtistArtKey(name, true)
            )
            if (portrait != null) return portrait
        }

        return GeneratedArtContentProvider.artUri(PlaylistArtKind.ARTIST, name.orEmpty(), tint)
    }
}
