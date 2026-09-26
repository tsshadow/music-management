package nl.teunschriks.mumamobile.api.subsonic.models

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * [TrackForm] is the gate every `form` value passes before `getSongs`: the server
 * (`parseTrackForms` in LMS) refuses anything outside track/set/liveset/podcast with an error for
 * the whole request, so an unknown value has to vanish here rather than cost the listener the list.
 */
class TrackFormTest {

    @Test
    fun `the forms are exactly the ones the server accepts`() {
        TrackForm.FORMS `should be equal to` listOf("track", "set", "liveset", "podcast")
        TrackForm.SET_FORMS `should be equal to` listOf("set", "liveset", "podcast")
    }

    @Test
    fun `a known form is read in the server's spelling`() {
        TrackForm.known(" LiveSet ") `should be equal to` "liveset"
    }

    @Test
    fun `anything else is not a form`() {
        TrackForm.known("mixtape").`should be null`()
        TrackForm.known("").`should be null`()
        TrackForm.known(null).`should be null`()
    }

    @Test
    fun `sanitize keeps the known forms once each, in order`() {
        TrackForm.sanitize(listOf("podcast", "mix", "SET", "podcast")) `should be equal to` listOf("podcast", "set")
    }

    @Test
    fun `sanitize answers null when nothing known is left, so no form is sent at all`() {
        TrackForm.sanitize(listOf("mixtape", " ")).`should be null`()
        TrackForm.sanitize(emptyList()).`should be null`()
        TrackForm.sanitize(null).`should be null`()
    }
}
