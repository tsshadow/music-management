/*
 * GenreTintsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import android.graphics.Color
import nl.teunschriks.mumamobile.api.muma.MumaLibraryGenre
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The colour a genre tile is drawn in comes from MuMa, not from a table in the app.
 *
 * The web UI reads the same field off the same endpoint. A second table here would drift from it,
 * and the difference -- Hardstyle orange in one place and magenta in the other -- is invisible
 * until both are open next to each other and untestable from either side.
 */
@RunWith(RobolectricTestRunner::class)
class GenreTintsTest {

    private val rows = listOf(
        MumaLibraryGenre(genre = "Hardstyle", count = 412, tint = "#ff4d00"),
        MumaLibraryGenre(genre = "Techno", count = 301, tint = "#00e0c7")
    )

    @Test
    fun `a genre is drawn in the colour the server sent`() {
        GenreTints.tintFor(GenreTints.parse(rows), "Hardstyle") `should be equal to` Color.parseColor("#ff4d00")
    }

    @Test
    fun `the name is matched whatever case it arrives in`() {
        // The Subsonic genre list and MuMa's own list do not agree on capitalisation.
        val tints = GenreTints.parse(rows)

        GenreTints.tintFor(tints, " HARDSTYLE ") `should be equal to` Color.parseColor("#ff4d00")
    }

    @Test
    fun `a genre the server did not mention falls back to the neutral tint`() {
        // Not a second table: one colour, so a tile is never drawn without one.
        GenreTints.tintFor(GenreTints.parse(rows), "Frenchcore") `should be equal to` GenreTints.FALLBACK
    }

    @Test
    fun `a row without a colour is ignored rather than parsed into black`() {
        // An older server answers without the field. `Color.parseColor` throws on an empty string,
        // and a genre drawn in black is a tile with an invisible name.
        val tints = GenreTints.parse(listOf(MumaLibraryGenre(genre = "Hardcore", count = 3, tint = null)))

        GenreTints.tintFor(tints, "Hardcore") `should be equal to` GenreTints.FALLBACK
    }

    @Test
    fun `a colour the server sent in a shape Android cannot read is ignored`() {
        val tints = GenreTints.parse(listOf(MumaLibraryGenre(genre = "Hardcore", count = 3, tint = "orange-ish")))

        GenreTints.tintFor(tints, "Hardcore") `should be equal to` GenreTints.FALLBACK
    }

    @Test
    fun `an empty answer leaves every genre on the fallback`() {
        GenreTints.tintFor(GenreTints.parse(emptyList()), "Hardstyle") `should be equal to` GenreTints.FALLBACK
    }
}
