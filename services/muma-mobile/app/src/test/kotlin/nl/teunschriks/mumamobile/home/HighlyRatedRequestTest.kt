@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.home

import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * What the "highly rated" section may ask the server for.
 *
 * The server knows a fixed set of cluster types and answers an unknown one with "not
 * found" -- for the whole request, not just that filter. RATING is not one of them; the
 * rating goes through ratingMin and ratingMax. Sending it as a cluster as well made this
 * section empty on every home screen that asked for it, silently, since the day it was
 * written.
 */
class HighlyRatedRequestTest {
    @Test
    fun `Should never send a rating as a cluster`() {
        val filters = Filters().apply { add(Filter("LENGTH", "short")) }

        filters.toString().contains("RATING") `should be equal to` false
    }
}
