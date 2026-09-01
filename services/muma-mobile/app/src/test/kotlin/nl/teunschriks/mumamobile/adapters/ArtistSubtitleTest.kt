package nl.teunschriks.mumamobile.adapters

import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Index
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The subtitle strings are localized (see `res/values/strings.xml` /
 * `res/values-nl/strings.xml`), so these assert against the resolved resources for the test's
 * locale rather than hardcoded English text - the fixture that would previously have passed
 * against literal "albums"/"tracks" regardless of what the app actually shows a Dutch user.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class, manifest = Config.NONE)
class ArtistSubtitleTest {

    private val context get() = RuntimeEnvironment.getApplication()

    private fun albums(count: Int): String = context.resources.getQuantityString(R.plurals.select_artist_subtitle_albums, count, count)

    private fun tracks(count: Int): String = context.resources.getQuantityString(R.plurals.select_artist_subtitle_tracks, count, count)

    @Test
    fun `both counts are shown when both are known`() {
        val artist = Artist(id = "ar-1", name = "Angerfist", albumCount = 12L, songCount = 143L)

        artistSubtitle(artist, context) `should be equal to` "${albums(12)} · ${tracks(143)}"
    }

    @Test
    fun `a single album is not pluralised`() {
        val artist = Artist(id = "ar-1", name = "Someone", albumCount = 1L, songCount = 1L)

        artistSubtitle(artist, context) `should be equal to` "${albums(1)} · ${tracks(1)}"
    }

    @Test
    fun `an unknown count is left out rather than shown as zero`() {
        val artist = Artist(id = "ar-1", name = "Someone", albumCount = 3L, songCount = null)

        artistSubtitle(artist, context) `should be equal to` albums(3)
    }

    @Test
    fun `a folder index has no subtitle`() {
        artistSubtitle(Index(id = "idx-1", name = "Hardcore"), context) `should be equal to` null
    }
}
