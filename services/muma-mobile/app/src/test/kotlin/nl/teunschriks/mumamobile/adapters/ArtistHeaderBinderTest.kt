/*
 * ArtistHeaderBinderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.adapters

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.appcompat.view.ContextThemeWrapper
import androidx.core.view.isVisible
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.util.Settings
import org.amshove.kluent.`should be equal to`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Binding is where the header meets real resources and a real Material theme, so this is what
 * catches a renamed view id or a FloatingActionButton that cannot inflate.
 *
 * Artist pictures are switched off for these tests: with them on, the binder resolves an
 * ImageLoaderProvider through Koin and starts a download, none of which this test is about.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class ArtistHeaderBinderTest {

    private lateinit var parent: ViewGroup

    @Before
    fun setUp() {
        Settings.shouldShowArtistPicture = false

        val themed = ContextThemeWrapper(RuntimeEnvironment.getApplication(), R.style.UltrasonicTheme_Spotify)
        parent = FrameLayout(themed)
    }

    private fun bind(
        header: ArtistHeader,
        onPlayAll: () -> Unit = {},
        onShowAllTracks: () -> Unit = {}
    ): ArtistHeaderBinder.ViewHolder {
        val binder = ArtistHeaderBinder(onPlayAll, onShowAllTracks)
        val inflater = LayoutInflater.from(parent.context)
        val holder = binder.onCreateViewHolder(inflater, parent)
        binder.onBindViewHolder(holder, header)
        return holder
    }

    private fun fullHeader() = ArtistHeader(
        name = "Angerfist",
        coverArtId = "ar-1-cover",
        subtitle = "12 albums · 143 tracks",
        years = "1998 – 2020",
        genres = "Hardcore, Uptempo"
    )

    @Test
    fun `every line is shown when every line has text`() {
        val holder = bind(fullHeader())

        holder.title.text.toString() `should be equal to` "Angerfist"
        holder.subtitle.text.toString() `should be equal to` "12 albums · 143 tracks"
        holder.years.text.toString() `should be equal to` "1998 – 2020"
        holder.genres.text.toString() `should be equal to` "Hardcore, Uptempo"
    }

    @Test
    fun `a line with nothing to say takes up no space`() {
        val holder = bind(
            ArtistHeader(name = "Someone", coverArtId = null, subtitle = null, years = null, genres = null)
        )

        holder.title.text.toString() `should be equal to` "Someone"
        holder.subtitle.isVisible `should be equal to` false
        holder.years.isVisible `should be equal to` false
        holder.genres.isVisible `should be equal to` false
    }

    @Test
    fun `a rebound holder does not keep the previous artist's lines`() {
        val binder = ArtistHeaderBinder(onPlayAll = {})
        val holder = binder.onCreateViewHolder(LayoutInflater.from(parent.context), parent)

        binder.onBindViewHolder(holder, fullHeader())
        binder.onBindViewHolder(
            holder,
            ArtistHeader(name = "Someone", coverArtId = null, subtitle = null, years = null, genres = null)
        )

        holder.years.isVisible `should be equal to` false
        holder.genres.isVisible `should be equal to` false
    }

    @Test
    fun `the play all button reports taps`() {
        var taps = 0
        val holder = bind(fullHeader(), onPlayAll = { taps++ })

        holder.playAll.performClick()

        taps `should be equal to` 1
    }

    @Test
    fun `the header offers every track, not only the albums`() {
        var showAllTracksCalled = false

        val holder = bind(
            ArtistHeader(
                name = "Headhunterz",
                coverArtId = null,
                subtitle = null,
                years = null,
                genres = null
            ),
            onShowAllTracks = { showAllTracksCalled = true }
        )

        holder.itemView.findViewById<View>(R.id.artist_all_tracks).performClick()

        showAllTracksCalled `should be equal to` true
    }
}
