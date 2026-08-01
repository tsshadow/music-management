package org.moire.ultrasonic.adapters

import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Index

class ArtistSubtitleTest {

    @Test
    fun `both counts are shown when both are known`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", albumCount = 12L, songCount = 143L)

        artistSubtitle(artist) `should be equal to` "12 albums · 143 tracks"
    }

    @Test
    fun `a single album is not pluralised`() {
        val artist = Artist(id = "ar-1", name = "Someone", albumCount = 1L, songCount = 1L)

        artistSubtitle(artist) `should be equal to` "1 album · 1 track"
    }

    @Test
    fun `an unknown count is left out rather than shown as zero`() {
        val artist = Artist(id = "ar-1", name = "Someone", albumCount = 3L, songCount = null)

        artistSubtitle(artist) `should be equal to` "3 albums"
    }

    @Test
    fun `a folder index has no subtitle`() {
        artistSubtitle(Index(id = "idx-1", name = "Hardcore")) `should be equal to` null
    }
}
