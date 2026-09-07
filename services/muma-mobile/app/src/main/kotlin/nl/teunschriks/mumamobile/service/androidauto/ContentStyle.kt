/*
 * ContentStyle.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.content.ContentResolver
import android.net.Uri
import android.os.Bundle
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaLibraryService

/**
 * The extras Android Auto reads to decide how a browse level is drawn.
 *
 * They are hints about the *children* of a level, which is why they travel on the level's
 * [MediaLibraryService.LibraryParams] rather than on the items themselves. Without them the car
 * draws every level as a text list with a generic icon, and any artwork the items carry is
 * ignored.
 *
 * The string keys are the ones from `androidx.media.utils.MediaConstants`, copied rather than
 * imported: the media-compat library is not on the classpath and the values are frozen -- the car
 * matches on the literal.
 */
internal const val CONTENT_STYLE_BROWSABLE_HINT =
    "android.media.browse.CONTENT_STYLE_BROWSABLE_HINT"
internal const val CONTENT_STYLE_PLAYABLE_HINT =
    "android.media.browse.CONTENT_STYLE_PLAYABLE_HINT"

internal const val CONTENT_STYLE_LIST_ITEM = 1
internal const val CONTENT_STYLE_GRID_ITEM = 2

/**
 * The layout for a level, decided by whether its browsable children have anything to show.
 *
 * A grid trades text for image: it fits fewer entries on a car screen and cuts the title short.
 * That is a good trade for albums, artists and anything else carrying cover art, and a bad one
 * for the alphabetic index the artist list falls back to, where every tile would be a letter on
 * an empty square. One entry with cover art is enough -- an album page appends a browsable "More"
 * entry that has no art of its own, and that entry must not drag the whole page back to a list.
 *
 * A menu icon does not count. The root's entries carry a monochrome vector from the drawables,
 * which as a grid tile is a small glyph on a large empty square and leaves the name -- the only
 * thing telling those entries apart -- less room than the list gave it.
 *
 * Playable children stay a list whatever they carry. A grid of forty tracks costs the driver more
 * glances than forty rows.
 */
@UnstableApi
internal fun contentStyleParams(items: List<MediaItem>): MediaLibraryService.LibraryParams {
    val browsableArtwork = items.any {
        it.mediaMetadata.isBrowsable == true && it.mediaMetadata.artworkUri.isCoverArt()
    }

    return MediaLibraryService.LibraryParams.Builder()
        .setExtras(
            Bundle().withContentStyle(
                browsable = if (browsableArtwork) CONTENT_STYLE_GRID_ITEM else CONTENT_STYLE_LIST_ITEM
            )
        )
        .build()
}

/**
 * Whether an artwork URI points at a picture of the music rather than at a drawable in the APK.
 */
private fun Uri?.isCoverArt(): Boolean = this != null && scheme != ContentResolver.SCHEME_ANDROID_RESOURCE

/**
 * Writes the two hints into a bundle that is being built for another reason.
 */
internal fun Bundle.withContentStyle(
    browsable: Int,
    playable: Int = CONTENT_STYLE_LIST_ITEM
): Bundle = apply {
    putInt(CONTENT_STYLE_BROWSABLE_HINT, browsable)
    putInt(CONTENT_STYLE_PLAYABLE_HINT, playable)
}
