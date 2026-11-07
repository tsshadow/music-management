/*
 * StationLogoProviderTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.provider

import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class StationLogoProviderTest {

    private fun slug(path: String) = StationLogoProvider.slugOf(Uri.parse("content://logos/$path"))

    @Test
    fun `a uri with one slug gives that slug`() {
        assertEquals("sky-radio-00s-10s", slug("sky-radio-00s-10s"))
    }

    @Test
    fun `any other path is refused`() {
        assertNull(slug("a/b"))
        assertNull(slug("..%2F..%2Fsecret"))
        assertNull(slug("UPPER"))
        assertNull(slug(""))
    }
}
