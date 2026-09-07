/*
 * BrowseArtworkTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.graphics.Color
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should not be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Which picture a browsable entry gets.
 *
 * A real photo always wins: an artist MuMa has a portrait for should show the portrait, not two
 * initials on a coloured square. The drawn cover is what stops the entries that have no photo from
 * dropping the whole level back to a text list.
 */
@RunWith(RobolectricTestRunner::class)
class BrowseArtworkTest {

    private val orange = Color.parseColor("#ff4d00")

    @Test
    fun `an artist with a portrait keeps the portrait`() {
        val art = BrowseArtwork.forArtist(coverArt = "ar-99", name = "Headhunterz", tint = orange)

        art!!.authority!!.endsWith("AlbumArtContentProvider") `should be equal to` true
    }

    @Test
    fun `an artist without a portrait gets one drawn from the name`() {
        val art = BrowseArtwork.forArtist(coverArt = null, name = "Headhunterz", tint = orange)

        art!!.authority!!.endsWith("GeneratedArtContentProvider") `should be equal to` true
    }

    @Test
    fun `an artist whose portrait id is blank is treated as having none`() {
        // The server sends an empty string rather than omitting the field, and an empty cover-art
        // id resolves to no picture at all.
        BrowseArtwork.forArtist(coverArt = "  ", name = "Headhunterz", tint = orange)
            ?.authority?.endsWith("GeneratedArtContentProvider") `should be equal to` true
    }

    @Test
    fun `an artist with neither portrait nor name gets nothing rather than a blank square`() {
        BrowseArtwork.forArtist(coverArt = null, name = "", tint = orange) `should be equal to` null
    }

    @Test
    fun `a genre is always drawn since it never has a picture of its own`() {
        BrowseArtwork.forGenre("Hardstyle", orange).`should not be null`()
    }
}
