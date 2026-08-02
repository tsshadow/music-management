package org.moire.ultrasonic.home

import android.content.SharedPreferences
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

class RecentActivityStoreTest {

    private fun card(id: String, type: HomeCardType = HomeCardType.ALBUM) =
        HomeCard(type = type, itemId = id, title = "T$id")

    private fun store(
        separatePerMode: Boolean = true,
        preferences: SharedPreferences = FakePreferences()
    ) = RecentActivityStore(preferences, separatePerMode = { separatePerMode })

    @Test
    fun `records newest first`() {
        val store = store()
        store.record(card("1"), setsMode = false)
        store.record(card("2"), setsMode = false)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("2", "1")
    }

    @Test
    fun `re-recording moves an item to the front without duplicating it`() {
        val store = store()
        store.record(card("1"), setsMode = false)
        store.record(card("2"), setsMode = false)
        store.record(card("1"), setsMode = false)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("1", "2")
    }

    @Test
    fun `same id but different type are distinct entries`() {
        val store = store()
        store.record(card("1", HomeCardType.ALBUM), setsMode = false)
        store.record(card("1", HomeCardType.ARTIST), setsMode = false)

        store.recent(setsMode = false).size `should be equal to` 2
    }

    @Test
    fun `trims to the maximum retained size`() {
        val store = store()
        repeat(30) { store.record(card("$it"), setsMode = false) }

        store.recent(setsMode = false, limit = 100).size `should be equal to` RecentActivityStore.MAX_ENTRIES
    }

    @Test
    fun `recent returns at most the default limit`() {
        val store = store()
        repeat(12) { store.record(card("$it"), setsMode = false) }

        store.recent(setsMode = false).size `should be equal to` RecentActivityStore.DEFAULT_LIMIT
    }

    @Test
    fun `separate per mode keeps songs and livesets apart`() {
        val store = store(separatePerMode = true)
        store.record(card("song"), setsMode = false)
        store.record(card("set"), setsMode = true)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("song")
        store.recent(setsMode = true).map { it.itemId } `should be equal to` listOf("set")
    }

    @Test
    fun `shared mode puts everything in one list`() {
        val store = store(separatePerMode = false)
        store.record(card("song"), setsMode = false)
        store.record(card("set"), setsMode = true)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("set", "song")
    }

    @Test
    fun `the whole card survives a round trip`() {
        val store = store()
        val original = HomeCard(
            type = HomeCardType.DYNAMIC_PLAYLIST,
            itemId = "t1",
            title = "Recent Hardstyle",
            subtitle = "Playlist",
            coverArtId = "cover",
            payload = """{"genre":["Hardstyle"]}"""
        )

        store.record(original, setsMode = false)

        store.recent(setsMode = false).first() `should be equal to` original
    }

    @Test
    fun `corrupt stored json yields an empty list instead of crashing`() {
        val preferences = FakePreferences()
        preferences.edit().putString("home_recent_songs", "{not json").apply()

        store(preferences = preferences).recent(setsMode = false) `should be equal to` emptyList()
    }

    @Test
    fun `updateCoverArt fills in the artwork of a stored card`() {
        val store = store()
        store.record(card("1", HomeCardType.ARTIST), setsMode = false)

        store.updateCoverArt("ARTIST:1", "muma-41-0", setsMode = false)

        store.recent(setsMode = false).single().coverArtId `should be equal to` "muma-41-0"
    }

    @Test
    fun `updateCoverArt keeps entries past the visible slice`() {
        val store = store()
        repeat(12) { store.record(card("$it"), setsMode = false) }

        store.updateCoverArt("ALBUM:0", "art-7-0", setsMode = false)

        store.recent(setsMode = false, limit = 100).size `should be equal to` 12
    }

    @Test
    fun `updateCoverArt ignores a card that is no longer stored`() {
        val store = store()
        store.record(card("1"), setsMode = false)

        store.updateCoverArt("ARTIST:nope", "muma-41-0", setsMode = false)

        store.recent(setsMode = false).single().coverArtId.shouldBeNull()
    }
}
