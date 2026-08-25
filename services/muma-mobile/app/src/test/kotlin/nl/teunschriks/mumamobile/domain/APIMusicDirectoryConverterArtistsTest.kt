/*
 * APIMusicDirectoryConverterArtistsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.domain

import nl.teunschriks.mumamobile.api.subsonic.models.ApiArtistRef
import nl.teunschriks.mumamobile.api.subsonic.models.MusicDirectoryChild
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The split artists, the moods and the label are only worth sending if they survive the step
 * from the API model to the entity the sheet reads. MusicDirectoryChildArtistsTest covers the
 * step before this one - the JSON.
 */
class APIMusicDirectoryConverterArtistsTest {

    @Test
    fun `the split artists survive the trip to the entity`() {
        val child = MusicDirectoryChild(
            id = "1",
            artist = "Headhunterz, Wildstylez",
            artistId = "ar-1",
            artists = listOf(
                ApiArtistRef("ar-1", "Headhunterz"),
                ApiArtistRef("ar-2", "Wildstylez")
            ),
            moods = listOf("energetic"),
            labels = listOf("Scantraxx")
        )

        val track = child.toTrackEntity(serverId = 1)

        track.artist `should be equal to` "Headhunterz, Wildstylez"
        track.artists `should be equal to` listOf(
            TrackArtistRef("ar-1", "Headhunterz"),
            TrackArtistRef("ar-2", "Wildstylez")
        )
        track.moods `should be equal to` listOf("energetic")
        track.labels `should be equal to` listOf("Scantraxx")
    }

    @Test
    fun `a server that sends none of it leaves the lists empty`() {
        val track = MusicDirectoryChild(id = "1", artist = "Deadmau5", artistId = "ar-9")
            .toTrackEntity(serverId = 1)

        track.artists `should be equal to` emptyList()
        track.moods `should be equal to` emptyList()
        track.labels `should be equal to` emptyList()
    }
}
