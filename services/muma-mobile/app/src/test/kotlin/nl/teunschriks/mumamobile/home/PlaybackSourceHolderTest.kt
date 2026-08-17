package nl.teunschriks.mumamobile.home

import android.content.SharedPreferences
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test

class PlaybackSourceHolderTest {

    private val preferences: SharedPreferences = FakePreferences()

    private fun holder() = PlaybackSourceHolder(preferences)

    private val rawHardstyle = HomeCard(
        type = HomeCardType.GENRE,
        itemId = "Raw Hardstyle",
        title = "Raw Hardstyle",
        payload = """{"length":"short","sortMethod":"OriginalDateDescAndRelease"}"""
    )

    @Test
    fun `nothing has been played yet`() {
        holder().current().shouldBeNull()
    }

    @Test
    fun `remembers the card the queue was filled from`() {
        holder().set(rawHardstyle)

        holder().current() `should be equal to` rawHardstyle
    }

    @Test
    fun `the stored source keeps its query, so replaying it re-runs the search`() {
        holder().set(rawHardstyle)

        holder().current()?.payload `should be equal to`
            """{"length":"short","sortMethod":"OriginalDateDescAndRelease"}"""
    }

    @Test
    fun `a queue with no source forgets the previous one`() {
        holder().set(rawHardstyle)

        holder().set(null)

        holder().current().shouldBeNull()
    }

    @Test
    fun `a corrupt stored source reads as no source at all`() {
        preferences.edit().putString("home_playback_source", "{not json").apply()

        holder().current().shouldBeNull()
    }
}
