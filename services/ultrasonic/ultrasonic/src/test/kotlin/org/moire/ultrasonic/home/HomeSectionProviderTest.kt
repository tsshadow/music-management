package org.moire.ultrasonic.home

import kotlinx.coroutines.runBlocking
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.moire.ultrasonic.R
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Label

class HomeSectionProviderTest {

    private fun provider(
        artists: () -> List<Artist> = { emptyList() },
        albums: () -> List<Album> = { emptyList() },
        labels: () -> List<Label> = { emptyList() }
    ) = LibraryActivityProvider(
        titleRes = R.string.home_recently_added,
        type = "newest",
        loadArtists = { artists() },
        loadAlbums = { albums() },
        loadLabels = { labels() }
    )

    @Test
    fun `interleaves artists albums and labels round robin`() = runBlocking<Unit> {
        val section = provider(
            artists = { listOf(Artist(id = "ar1", name = "A1"), Artist(id = "ar2", name = "A2")) },
            albums = { listOf(Album(id = "al1", title = "L1"), Album(id = "al2", title = "L2")) },
            labels = { listOf(Label(id = "lb1", name = "B1"), Label(id = "lb2", name = "B2")) }
        ).load()!!

        section.style `should be equal to` CardStyle.CAROUSEL
        section.cards.map { it.type } `should be equal to` listOf(
            HomeCardType.ARTIST,
            HomeCardType.ALBUM,
            HomeCardType.LABEL,
            HomeCardType.ARTIST,
            HomeCardType.ALBUM,
            HomeCardType.LABEL
        )
    }

    @Test
    fun `keeps going when one type returns nothing`() = runBlocking<Unit> {
        val section = provider(
            albums = { listOf(Album(id = "al1", title = "L1"), Album(id = "al2", title = "L2")) },
            labels = { listOf(Label(id = "lb1", name = "B1")) }
        ).load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("al1", "B1", "al2")
    }

    @Test
    fun `a failing source does not sink the whole section`() = runBlocking<Unit> {
        val section = provider(
            artists = { error("offline") },
            albums = { listOf(Album(id = "al1", title = "L1")) }
        ).load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("al1")
    }

    @Test
    fun `returns null when every type fails or is empty`() = runBlocking<Unit> {
        provider(artists = { error("offline") }, labels = { error("offline") }).load()
            .shouldBeNull()
    }
}
