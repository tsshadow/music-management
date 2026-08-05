/*
 * MediaLibraryMusicServiceResolutionTest.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.amshove.kluent.`should be`
import org.junit.Test
import nl.teunschriks.mumamobile.service.MusicService

/**
 * The Android Auto browse stack must resolve the [MusicService] on every access instead of
 * capturing one instance when the media session is created. `MusicServiceFactory.resetMusicService()`
 * (server switch, credential edit, network coming back) replaces the Koin-provided instance, and
 * `getMusicService()` may hand back the offline service while the server is unreachable. A captured
 * instance leaves Android Auto stuck with a dead or offline service for the lifetime of the process
 * while the phone UI - which resolves per call - recovers.
 */
class MediaLibraryMusicServiceResolutionTest {

    private val firstService: MusicService = mockk(relaxed = true)
    private val secondService: MusicService = mockk(relaxed = true)

    private var currentService: MusicService = firstService
    private val provider: () -> MusicService = { currentService }

    private val scope = CoroutineScope(Dispatchers.Unconfined)

    @Test
    fun `data provider resolves the current music service on every access`() {
        val dataProvider = MediaLibraryDataProvider(
            serviceScope = scope,
            musicServiceProvider = provider
        )

        dataProvider.musicService `should be` firstService

        currentService = secondService

        dataProvider.musicService `should be` secondService
    }

    @Test
    fun `playback controller resolves the current music service on every access`() {
        val controller = MediaLibraryPlaybackController(
            serviceScope = scope,
            musicServiceProvider = provider
        )

        controller.musicService `should be` firstService

        currentService = secondService

        controller.musicService `should be` secondService
    }

    @Test
    fun `browser resolves the current music service on every access`() {
        val browser = MediaLibraryBrowser(
            mainScope = scope,
            serviceScope = scope,
            musicServiceProvider = provider
        )

        browser.musicService `should be` firstService

        currentService = secondService

        browser.musicService `should be` secondService
    }
}
