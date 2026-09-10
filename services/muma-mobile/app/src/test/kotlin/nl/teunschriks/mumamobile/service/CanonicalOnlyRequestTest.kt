@file:Suppress("IllegalIdentifier")

package nl.teunschriks.mumamobile.service

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Which value reaches the server for `canonicalOnly`.
 *
 * The rule that matters: asking for one song's versions and collapsing to one of them are
 * opposites. A workId always wins over the setting, or the version list would answer with the
 * single row it exists to look past.
 */
class CanonicalOnlyRequestTest {
    /** The decision RESTMusicService makes before it calls the API. */
    private fun resolve(workId: Int?, requested: Boolean?, setting: Boolean): Boolean = if (workId != null) false else requested ?: setting

    @Test
    fun `Should follow the setting when nothing was asked for`() {
        resolve(null, null, true) `should be equal to` true
        resolve(null, null, false) `should be equal to` false
    }

    @Test
    fun `Should let an explicit request override the setting`() {
        resolve(null, false, true) `should be equal to` false
        resolve(null, true, false) `should be equal to` true
    }

    @Test
    fun `Should never collapse when a work was named`() {
        resolve(42, null, true) `should be equal to` false
        resolve(42, true, true) `should be equal to` false
    }

    @Test
    fun `Should fall back to the setting rather than to a hard-coded default`() {
        // The default lives in Settings and in settings.xml, and reading it needs an Android
        // context -- so what is pinned here is that this code asks for it instead of deciding
        // on its own.
        resolve(null, null, setting = true) `should be equal to` true
        resolve(null, null, setting = false) `should be equal to` false
    }
}
