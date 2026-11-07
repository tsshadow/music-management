/*
 * CachedDataSourceHeadersTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DataSpec
import androidx.media3.extractor.metadata.icy.IcyHeaders
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkObject
import io.mockk.unmockkObject
import io.mockk.verify
import java.io.IOException
import nl.teunschriks.mumamobile.util.Storage
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
class CachedDataSourceHeadersTest {

    /** The custom cache folder of a phone: it throws for a path outside that folder. */
    @Before
    fun setUp() {
        mockkObject(Storage)
        every { Storage.isPathExists(any()) } throws IOException("the root has changed")
    }

    @After
    fun tearDown() {
        unmockkObject(Storage)
    }

    /** Report 44: the stream failed in a millisecond, before any request left the phone. */
    @Test
    fun `a live stream opens without asking the storage`() {
        val upstream = mockk<DataSource>(relaxed = true)
        every { upstream.open(any()) } returns C.LENGTH_UNSET.toLong()
        val stream = DataSpec(Uri.parse("https://example.com/redirect/Q_DANCE.mp3"))

        CachedDataSource(upstream).open(stream) shouldBeEqualTo C.LENGTH_UNSET.toLong()

        verify(exactly = 1) { upstream.open(stream) }
        verify(exactly = 0) { Storage.isPathExists(any()) }
    }

    /** A library track still looks for its file first. */
    @Test
    fun `a library track still asks the storage`() {
        every { Storage.isPathExists(any()) } returns false
        val upstream = mockk<DataSource>(relaxed = true)

        CachedDataSource(upstream).open(DataSpec(Uri.parse("tr-1|0|/music/track.mp3")))

        verify { Storage.isPathExists("/music/track.mp3") }
    }

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
