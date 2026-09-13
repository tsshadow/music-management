/*
 * LegacyPlaylistFilesTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import java.io.File
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.util.FileUtil.getCompleteFile
import org.amshove.kluent.shouldBeEmpty
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * A `.m3u` file is all a playlist downloaded before [nl.teunschriks.mumamobile.domain.OfflinePlaylist]
 * existed left behind: a display name and one path per track, nothing that ties it to the
 * server's own playlist id. [LegacyPlaylistFiles] is what lets such a playlist still show up once
 * that Room table is the source everything else reads from.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class LegacyPlaylistFilesTest {

    @get:Rule
    val folder = TemporaryFolder()

    private lateinit var directory: File

    private val trackOne = Track(id = "tr-1", serverId = 1, title = "One", path = "Artist/Album/One.mp3")
    private val trackTwo = Track(id = "tr-2", serverId = 1, title = "Two", path = "Artist/Album/Two.mp3")

    @Before
    fun setUp() {
        directory = folder.newFolder("playlists")
    }

    private fun writeM3u(name: String, lines: List<String>): File {
        val file = File(directory, "$name.m3u")
        file.writeText("#EXTM3U\n" + lines.joinToString("\n"))
        return file
    }

    @Test
    fun `a m3u file with no Room row becomes a playlist under a synthetic id`() {
        writeM3u("Warm-up", listOf(trackOne.getCompleteFile(), trackTwo.getCompleteFile()))

        val records = LegacyPlaylistFiles.read(directory, knownNames = emptySet(), tracks = listOf(trackOne, trackTwo))

        records.size shouldBeEqualTo 1
        val record = records.first()
        record.name shouldBeEqualTo "Warm-up"
        record.trackIds shouldBeEqualTo listOf("tr-1", "tr-2")
        record.id.startsWith("legacy:") shouldBeEqualTo true
    }

    @Test
    fun `the synthetic id is the same across two reads of the same file`() {
        writeM3u("Warm-up", listOf(trackOne.getCompleteFile()))

        val first = LegacyPlaylistFiles.read(directory, emptySet(), listOf(trackOne)).first().id
        val second = LegacyPlaylistFiles.read(directory, emptySet(), listOf(trackOne)).first().id

        first shouldBeEqualTo second
    }

    @Test
    fun `a playlist already covered by a Room row is not listed a second time`() {
        writeM3u("Warm-up", listOf(trackOne.getCompleteFile()))

        val records = LegacyPlaylistFiles.read(directory, knownNames = setOf("Warm-up"), tracks = listOf(trackOne))

        records.shouldBeEmpty()
    }

    @Test
    fun `a line that matches no known track is dropped rather than failing the whole file`() {
        writeM3u("Warm-up", listOf(trackOne.getCompleteFile(), "/some/other/device/Missing.mp3"))

        val records = LegacyPlaylistFiles.read(directory, emptySet(), listOf(trackOne))

        records.first().trackIds shouldBeEqualTo listOf("tr-1")
    }

    @Test
    fun `a directory with no m3u files answers no playlists`() {
        LegacyPlaylistFiles.read(directory, emptySet(), listOf(trackOne)).shouldBeEmpty()
    }
}
