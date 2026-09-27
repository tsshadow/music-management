/*
 * MediaLibraryDailyMixesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import nl.teunschriks.mumamobile.api.muma.MumaAPIDefinition
import nl.teunschriks.mumamobile.api.muma.MumaFeedInfo
import nl.teunschriks.mumamobile.api.muma.MumaFeedList
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.util.SignedInFixture
import org.amshove.kluent.`should be equal to`
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import retrofit2.Call
import retrofit2.Response

/**
 * The car's "Daily mixes" folder: the five mixes on the hardness spectrum and the day's artist
 * and label, with the classic, unrestricted mix last.
 *
 * Titles come from `GET /api/feeds` (the same `describe_feed` the phone and web read), so the
 * folder is only ever as informative as the server -- a listener with no artist affinity yet
 * still gets a name, just the server's own fallback ("Artiestmix") rather than a blank row.
 */
@RunWith(RobolectricTestRunner::class)
class MediaLibraryDailyMixesTest {

    /** Signed in with a token, so the car's token gate lets the browse through (issue #115). */
    @Before
    fun signedInWithToken() = SignedInFixture.install()

    private val api: MumaAPIDefinition = mockk()
    private val musicService: MusicService = mockk(relaxed = true)
    private val scope = CoroutineScope(Dispatchers.Unconfined)
    private val feedRepository = FeedRepository({ api }, { musicService })
    private val browser = MediaLibraryBrowser(mainScope = scope, serviceScope = scope, musicServiceProvider = { musicService }).apply {
        dataProvider = MediaLibraryDataProvider(scope, { musicService }, { feedRepository })
    }

    private val session: MediaLibraryService.MediaLibrarySession = mockk(relaxed = true)
    private val controller: MediaSession.ControllerInfo = mockk(relaxed = true)

    private fun answering(feeds: List<MumaFeedInfo>?) {
        val call: Call<MumaFeedList> = mockk()
        every { call.execute() } returns Response.success(feeds?.let { MumaFeedList(it) })
        every { api.getFeeds() } returns call
    }

    private fun childIds(parentId: String): List<String> {
        val result = browser.getChildren(session, controller, parentId, 0, 50, null).get()
        return result.value!!.map { it.mediaId }
    }

    private fun children(parentId: String): List<MediaItem> {
        val result = browser.getChildren(session, controller, parentId, 0, 50, null).get()
        return result.value!!.toList()
    }

    @Test
    fun `the folder lists the spectrum, the two rotating mixes, then the classic mix last`() {
        answering(
            listOf(
                MumaFeedInfo(slug = "daily-mix-soft", title = "Zachter"),
                MumaFeedInfo(slug = "daily-mix-mid", title = "Middenin"),
                MumaFeedInfo(slug = "daily-mix-hard", title = "Harder"),
                MumaFeedInfo(slug = "daily-mix-artist", title = "Angerfist"),
                MumaFeedInfo(slug = "daily-mix-label", title = "Neophyte Records"),
                MumaFeedInfo(slug = "daily-mix", title = "Klassiek")
            )
        )

        val ids = childIds(MediaLibraryBase.MEDIA_DAILY_MIXES_ID)

        ids `should be equal to` listOf(
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-soft",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-mid",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-hard",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-artist",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-label",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix"
        )
    }

    @Test
    fun `every entry is directly playable, not a folder of its own`() {
        answering(listOf(MumaFeedInfo(slug = "daily-mix-soft", title = "Zachter")))

        val items = children(MediaLibraryBase.MEDIA_DAILY_MIXES_ID)

        items.all { it.mediaMetadata.isBrowsable != true } `should be equal to` true
    }

    @Test
    fun `titles come from the server, never a slug shown raw when one answers`() {
        answering(listOf(MumaFeedInfo(slug = "daily-mix-soft", title = "Zachter")))

        val items = children(MediaLibraryBase.MEDIA_DAILY_MIXES_ID)

        items.first().mediaMetadata.title.toString() `should be equal to` "Zachter"
    }

    @Test
    fun `a slug the list never mentioned still gets a row -- its own slug as the title`() {
        // The list call can fail independently of the six feeds actually existing on the server;
        // a folder that went empty because of that would look like the feature disappeared.
        answering(null)

        val ids = childIds(MediaLibraryBase.MEDIA_DAILY_MIXES_ID)

        ids `should be equal to` listOf(
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-soft",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-mid",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-hard",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-artist",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix-label",
            "${MediaLibraryBase.MEDIA_FEED_ID}|daily-mix"
        )
    }

    @Test
    fun `the classic mix's title never leaks onto a spectrum band`() {
        // Titles are looked up per exact slug -- a list that only mentions "daily-mix" must not
        // leave "daily-mix-mid" showing "Klassiek" instead of its own slug.
        answering(listOf(MumaFeedInfo(slug = "daily-mix", title = "Klassiek")))

        val items = children(MediaLibraryBase.MEDIA_DAILY_MIXES_ID)

        items[1].mediaMetadata.title.toString() `should be equal to` "daily-mix-mid"
        items.last().mediaMetadata.title.toString() `should be equal to` "Klassiek"
    }
}
