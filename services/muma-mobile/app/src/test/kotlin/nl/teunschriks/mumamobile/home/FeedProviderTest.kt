/*
 * FeedProviderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import kotlinx.coroutines.runBlocking
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.FeedRepository
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * One personalized feed as a section on the phone's home screen.
 *
 * The two claims worth pinning: the order is MuMa's and truncation takes the head of it, and an
 * empty feed hides the section instead of leaving yesterday's radar on screen. The second one
 * matters because the view model treats null and a thrown exception differently -- null clears the
 * cache, a throw keeps it -- and a feed that is genuinely empty this week must take the first path.
 */
class FeedProviderTest {

    private fun provider(
        rows: Int = 5,
        slug: String = FeedRepository.RELEASE_RADAR,
        load: suspend (String) -> List<Track>
    ) = FeedProvider(
        titleRes = R.string.home_release_radar,
        slug = slug,
        rows = { rows },
        loadFeed = load
    )

    private fun track(id: String) = Track(id = id, title = "T$id")

    @Test
    fun `the feed is shown in the order MuMa returned it`() = runBlocking<Unit> {
        val section = provider { listOf(track("3"), track("1"), track("2")) }.load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("3", "1", "2")
    }

    @Test
    fun `only the rows that fit are kept, and they are the top of the ranking`() = runBlocking<Unit> {
        // The quota per genre is filled from the top, so the head of the list is the strongest
        // pick in the largest share of the listener's taste. Any other slice would be arbitrary.
        val section = provider(rows = 2) { (1..5).map { track(it.toString()) } }.load()!!

        section.cards.map { it.itemId } `should be equal to` listOf("1", "2")
    }

    @Test
    fun `an empty feed hides the section rather than showing an empty one`() = runBlocking<Unit> {
        provider { emptyList() }.load().`should be null`()
    }

    @Test
    fun `the section is a list, like the track sections beside it`() = runBlocking<Unit> {
        val section = provider { listOf(track("1")) }.load()!!

        section.style `should be equal to` CardStyle.LIST
    }

    @Test
    fun `each feed caches under its own key`() {
        provider(slug = FeedRepository.RELEASE_RADAR) { emptyList() }.cacheKey `should be equal to` "feed:release-radar"
        provider(slug = FeedRepository.DAILY_MIX) { emptyList() }.cacheKey `should be equal to` "feed:daily-mix"
    }

    @Test
    fun `the slug it was built with is the one it asks for`() = runBlocking<Unit> {
        var asked: String? = null

        provider(slug = FeedRepository.DAILY_MIX) { slug ->
            asked = slug
            listOf(track("1"))
        }.load()

        asked `should be equal to` FeedRepository.DAILY_MIX
    }
}
