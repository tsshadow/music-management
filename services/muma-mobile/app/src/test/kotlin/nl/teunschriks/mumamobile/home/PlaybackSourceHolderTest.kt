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

    private val uptempo = HomeCard(
        type = HomeCardType.GENRE,
        itemId = "Uptempo",
        title = "Uptempo"
    )

    @Test
    fun `nothing has been played yet`() {
        holder().current().shouldBeNull()
    }

    @Test
    fun `remembers the card the queue was filled from`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().current() `should be equal to` rawHardstyle
    }

    @Test
    fun `arming alone is not playing yet`() {
        holder().arm(rawHardstyle)

        holder().current().shouldBeNull()
    }

    @Test
    fun `the stored source keeps its query, so replaying it re-runs the search`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().current()?.payload `should be equal to`
            """{"length":"short","sortMethod":"OriginalDateDescAndRelease"}"""
    }

    @Test
    fun `a queue nothing armed forgets the previous source`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().startQueue()

        holder().current().shouldBeNull()
    }

    @Test
    fun `a screen that is no place to go back to arms nothing`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().arm(null)
        holder().startQueue()

        holder().current().shouldBeNull()
    }

    @Test
    fun `the next queue replaces the source of the last one`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().arm(uptempo)
        holder().startQueue()

        holder().current() `should be equal to` uptempo
    }

    @Test
    fun `an append discards the arming instead of letting it wait for the next queue`() {
        holder().arm(rawHardstyle)

        holder().discardArmed()
        holder().startQueue()

        holder().current().shouldBeNull()
    }

    @Test
    fun `an append leaves the source of the queue it added to alone`() {
        holder().arm(rawHardstyle)
        holder().startQueue()

        holder().discardArmed()

        holder().current() `should be equal to` rawHardstyle
    }

    @Test
    fun `an armed source survives the process, because playback does`() {
        holder().arm(rawHardstyle)

        holder().startQueue()

        PlaybackSourceHolder(preferences).current() `should be equal to` rawHardstyle
    }

    @Test
    fun `a corrupt stored source reads as no source at all`() {
        preferences.edit().putString("home_playback_source", "{not json").apply()

        holder().current().shouldBeNull()
    }
}
