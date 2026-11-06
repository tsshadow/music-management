/*
 * CachedDataSourceHeadersTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import androidx.media3.datasource.DataSource
import androidx.media3.extractor.metadata.icy.IcyHeaders
import io.mockk.every
import io.mockk.mockk
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
class CachedDataSourceHeadersTest {

    /**
     * A live station interleaves text in the audio every `icy-metaint` bytes. Media3 can only take
     * that text out when it sees the header through this class, which wraps the HTTP source.
     */
    @Test
    fun `media3 sees the metadata interval of a live stream`() {
        val upstream = mockk<DataSource>(relaxed = true)
        every { upstream.responseHeaders } returns mapOf("icy-metaint" to listOf("16000"))

        val headers = IcyHeaders.parse(CachedDataSource(upstream).responseHeaders)

        headers?.metadataInterval shouldBeEqualTo 16000
    }
}
