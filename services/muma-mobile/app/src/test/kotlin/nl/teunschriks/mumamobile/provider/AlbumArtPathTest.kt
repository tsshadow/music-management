/*
 * AlbumArtPathTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.provider

import java.io.File
import java.nio.file.Files
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldBeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

/**
 * The exported album-art provider appended its key to the cache directory unchecked, so
 * `../../shared_prefs/<package>_preferences.xml` read the stored password (bug report 037).
 */
class AlbumArtPathTest {

    @get:Rule
    val temp = TemporaryFolder()

    @Test
    fun `a key the app builds itself is accepted`() {
        AlbumArtPath.isSafeCacheKey("0cc175b9c0f1b6a831c399e269772661.jpeg").shouldBeTrue()
        AlbumArtPath.isSafeCacheKey("0cc175b9c0f1b6a831c399e269772661.jpeg-small").shouldBeTrue()
    }

    @Test
    fun `a key that could leave the directory is refused`() {
        listOf(
            "../../shared_prefs/nl.teunschriks.mumamobile_preferences.xml",
            "..",
            "a/b.jpeg",
            "a\\b.jpeg",
            "/etc/passwd",
            "x..jpeg",
            "nul\u0000.jpeg",
            "",
            "   "
        ).forEach { key ->
            AlbumArtPath.isSafeCacheKey(key).shouldBeFalse()
        }
    }

    @Test
    fun `a safe key resolves to a file directly inside the directory`() {
        val dir = temp.newFolder("artwork")

        val resolved = AlbumArtPath.resolve(dir, "abc.jpeg")

        resolved shouldBeEqualTo File(dir.canonicalFile, "abc.jpeg")
    }

    @Test
    fun `the traversal from the report resolves to nothing`() {
        val dir = temp.newFolder("files", "muma", "artwork")
        temp.newFolder("shared_prefs")
        File(temp.root, "shared_prefs/nl.teunschriks.mumamobile_preferences.xml").writeText("<map/>")

        AlbumArtPath.resolve(dir, "../../../shared_prefs/nl.teunschriks.mumamobile_preferences.xml").shouldBeNull()
    }

    @Test
    fun `a symlink inside the directory that points out of it is refused`() {
        val dir = temp.newFolder("artwork")
        val secret = temp.newFile("secret.xml")
        Files.createSymbolicLink(File(dir, "link.jpeg").toPath(), secret.toPath())

        AlbumArtPath.resolve(dir, "link.jpeg").shouldBeNull()
    }

    @Test
    fun `the directory itself is not a file inside it`() {
        val dir = temp.newFolder("artwork")

        AlbumArtPath.resolve(dir, ".").shouldBeNull()
    }
}
