package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.junit.Test

class PlayHistoryTest {

    private val genres = mutableMapOf(false to "[]", true to "[]")
    private val store = RecentActivityStore(FakePreferences(), separatePerMode = { true })

    private fun recorder(
        setsMode: Boolean = false,
        source: () -> HomeCard? = { null }
    ) = PlayHistoryRecorder(
        store = store,
        setsMode = { setsMode },
        source = source,
        readGenres = { live -> genres.getValue(live) },
        writeGenres = { live, json -> genres[live] = json }
    )

    private val rawHardstyle = HomeCard(
        type = HomeCardType.GENRE,
        itemId = "Raw Hardstyle",
        title = "Raw Hardstyle"
    )

    private fun track(
        id: String = "t1",
        genre: String? = "Hardcore",
        genreList: List<String>? = null,
        duration: Int? = 300,
        albumId: String? = "a1"
    ) = Track(
        id = id,
        title = "Track $id",
        album = "Album $albumId",
        albumId = albumId,
        artist = "Artist",
        genre = genre,
        genres = genreList,
        duration = duration,
        coverArt = "cover-$id"
    )

    @Test
    fun `playing a song records its genre`() {
        recorder().record(track())

        genres.getValue(false) `should be equal to` """["Hardcore"]"""
    }

    @Test
    fun `a combined genre field is split into separate genres`() {
        recorder().record(track(genre = "Hardcore; Uptempo / Frenchcore"))

        genres.getValue(false) `should be equal to` """["Hardcore","Uptempo","Frenchcore"]"""
    }

    @Test
    fun `the genre list stays newest first without duplicates`() {
        val recorder = recorder()
        recorder.record(track(id = "1", genre = "Techno"))
        recorder.record(track(id = "2", genre = "Hardcore"))
        recorder.record(track(id = "3", genre = "Techno"))

        genres.getValue(false) `should be equal to` """["Techno","Hardcore"]"""
    }

    @Test
    fun `the genre list is capped`() {
        val recorder = recorder()
        repeat(MAX_LAST_PLAYED_GENRES + 5) { recorder.record(track(id = "$it", genre = "G$it")) }

        parseGenres(genres.getValue(false)).size `should be equal to` MAX_LAST_PLAYED_GENRES
    }

    @Test
    fun `a long track counts as a live set and uses the other genre list`() {
        recorder().record(track(genre = "Hardstyle", duration = 60 * 60))

        genres.getValue(true) `should be equal to` """["Hardstyle"]"""
        genres.getValue(false) `should be equal to` "[]"
    }

    @Test
    fun `the tag list wins over the single genre field when both are set`() {
        recorder().record(track(genre = "Hardcore", genreList = listOf("Raw", "Uptempo")))

        genres.getValue(false) `should be equal to` """["Raw","Uptempo"]"""
    }

    @Test
    fun `a track without a genre records neither a genre nor a shortcut`() {
        recorder().record(track(genre = null))

        genres.getValue(false) `should be equal to` "[]"
        store.recent(setsMode = false) `should be equal to` emptyList()
    }

    @Test
    fun `a corrupt stored genre list is replaced rather than dropping the play`() {
        genres[false] = "{not json"

        recorder().record(track(genre = "Techno"))

        genres.getValue(false) `should be equal to` """["Techno"]"""
    }

    @Test
    fun `the list the queue came from is recorded, not the track's album`() {
        recorder(source = { rawHardstyle }).record(track(albumId = "a1"))

        val card = store.recent(setsMode = false).single()
        card.type `should be equal to` HomeCardType.GENRE
        card.itemId `should be equal to` "Raw Hardstyle"
    }

    @Test
    fun `several tracks out of one list record a single shortcut`() {
        val recorder = recorder(source = { rawHardstyle })
        recorder.record(track(id = "1", albumId = "a1"))
        recorder.record(track(id = "2", albumId = "a2"))

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("Raw Hardstyle")
    }

    @Test
    fun `starting a queue records the shortcut straight away, without waiting for a scrobble`() {
        recorder(source = { rawHardstyle }).recordQueueStart()

        store.recent(setsMode = false).single().itemId `should be equal to` "Raw Hardstyle"
    }

    @Test
    fun `a queue with no place behind it records nothing, not the album of its tracks`() {
        val recorder = recorder(source = { null })

        recorder.recordQueueStart()
        recorder.record(track(albumId = "a1"))

        store.recent(setsMode = false) `should be equal to` emptyList()
    }

    @Test
    fun `the scrobble that follows the start of a queue does not add a second card`() {
        val recorder = recorder(source = { rawHardstyle })

        recorder.recordQueueStart()
        recorder.record(track(id = "1"))

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("Raw Hardstyle")
    }

    @Test
    fun `starting a queue leaves the genre lists to the tracks that actually play`() {
        recorder().recordQueueStart()

        genres.getValue(false) `should be equal to` "[]"
    }

    @Test
    fun `an album screen still records the album, because that is where playback started`() {
        val albumCard = HomeCard(type = HomeCardType.ALBUM, itemId = "a1", title = "Renegades")

        recorder(source = { albumCard }).recordQueueStart()

        val card = store.recent(setsMode = false).single()
        card.type `should be equal to` HomeCardType.ALBUM
        card.itemId `should be equal to` "a1"
    }

    @Test
    fun `the newest place is at the front of the home grid`() {
        var current: HomeCard? = rawHardstyle
        val recorder = recorder(source = { current })

        recorder.recordQueueStart()
        current = HomeCard(type = HomeCardType.LABEL, itemId = "Art of Creation", title = "Art of Creation")
        recorder.recordQueueStart()

        store.recent(setsMode = false).map { it.itemId } `should be equal to`
            listOf("Art of Creation", "Raw Hardstyle")
    }

    @Test
    fun `the place is filed under the current mode, not the track length`() {
        recorder(setsMode = true, source = { rawHardstyle }).record(track(duration = 300))

        store.recent(setsMode = true).map { it.itemId } `should be equal to` listOf("Raw Hardstyle")
        store.recent(setsMode = false) `should be equal to` emptyList()
    }

    private fun parseGenres(json: String): List<String> = json.trim('[', ']').split(",").filter { it.isNotBlank() }
}
