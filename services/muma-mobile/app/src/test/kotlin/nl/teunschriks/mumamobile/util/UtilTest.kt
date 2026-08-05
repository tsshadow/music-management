package nl.teunschriks.mumamobile.util

import java.io.Closeable
import java.io.IOException
import nl.teunschriks.mumamobile.util.Util.ifNotNull
import nl.teunschriks.mumamobile.util.Util.safeClose
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be false`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should be true`
import org.amshove.kluent.`should match`
import org.junit.Test

/**
 * The plain-JVM helpers in [Util]: no Android runtime is involved, so these run
 * without Robolectric.
 *
 * The byte sizes are asserted against a pattern rather than a literal: the
 * DecimalFormat behind them uses the JVM's default locale, so the decimal
 * separator is a comma on a Dutch machine and a dot on the runner.
 */
class UtilTest {

    @Test
    fun `bytes below a kilobyte are reported as they are`() {
        Util.formatBytes(0) `should be equal to` "0 B"
        Util.formatBytes(1023) `should be equal to` "1023 B"
    }

    @Test
    fun `kilobytes are reported without decimals`() {
        Util.formatBytes(1024) `should be equal to` "1 KB"
        Util.formatBytes(1024L * 512) `should be equal to` "512 KB"
    }

    @Test
    fun `megabytes are reported with two decimals`() {
        Util.formatBytes(1024L * 1024) `should match` "1[.,]00 MB"
        Util.formatBytes(1024L * 1024 * 3 / 2) `should match` "1[.,]50 MB"
    }

    @Test
    fun `gigabytes are reported with two decimals`() {
        Util.formatBytes(1024L * 1024 * 1024) `should match` "1[.,]00 GB"
    }

    @Test
    fun `hex encoding a string yields its utf-8 bytes`() {
        Util.utf8HexEncode("abc") `should be equal to` "616263"
    }

    @Test
    fun `hex encoding covers multi-byte characters`() {
        Util.utf8HexEncode("é") `should be equal to` "c3a9"
    }

    @Test
    fun `hex encoding nothing yields nothing`() {
        Util.utf8HexEncode(null).`should be null`()
    }

    @Test
    fun `an md5 is a 32 character hex digest`() {
        Util.md5Hex("abc") `should be equal to` "900150983cd24fb0d6963f7d28e17f72"
    }

    @Test
    fun `the md5 of nothing is nothing`() {
        Util.md5Hex(null).`should be null`()
    }

    @Test
    fun `the grandparent of a path is its top level folder`() {
        Util.getGrandparent("Angerfist/Close Combat/01 Raise Your Fist.mp3") `should be equal to` "Angerfist"
    }

    @Test
    fun `a path without a folder has no grandparent`() {
        Util.getGrandparent("track.mp3").`should be null`()
        Util.getGrandparent("/leading-slash").`should be null`()
        Util.getGrandparent(null).`should be null`()
    }

    @Test
    fun `a scaled height keeps the aspect ratio of the original`() {
        Util.getScaledHeight(200.0, 100.0, 50) `should be equal to` 100
        Util.getScaledHeight(100.0, 100.0, 300) `should be equal to` 300
    }

    @Test
    fun `a scaled height is rounded to whole pixels`() {
        Util.getScaledHeight(101.0, 100.0, 100) `should be equal to` 101
    }

    @Test
    fun `blank strings are recognised as empty`() {
        Util.isNullOrWhiteSpace(null).`should be true`()
        Util.isNullOrWhiteSpace("").`should be true`()
        Util.isNullOrWhiteSpace("   ").`should be true`()
        Util.isNullOrWhiteSpace("\t\n").`should be true`()
    }

    @Test
    fun `a string with content is not empty`() {
        Util.isNullOrWhiteSpace(" a ").`should be false`()
    }

    @Test
    fun `a duration under a minute is shown as seconds`() {
        Util.formatTotalDuration(9) `should be equal to` "0:09"
    }

    @Test
    fun `a duration in minutes drops the leading zero until ten minutes`() {
        Util.formatTotalDuration(65) `should be equal to` "1:05"
        Util.formatTotalDuration(605) `should be equal to` "10:05"
    }

    @Test
    fun `a duration over an hour includes the hours`() {
        Util.formatTotalDuration(3665) `should be equal to` "1:01:05"
    }

    @Test
    fun `a duration over ten hours pads the hours`() {
        Util.formatTotalDuration(36065) `should be equal to` "10:01:05"
    }

    @Test
    fun `a duration can be given in milliseconds instead`() {
        Util.formatTotalDuration(65000, true) `should be equal to` "1:05"
    }

    @Test
    fun `no duration is shown as nothing`() {
        Util.formatTotalDuration(null) `should be equal to` ""
    }

    @Test
    fun `accents are stripped from a name`() {
        Util.stripAccents("Frenchcöre") `should be equal to` "Frenchcore"
        Util.stripAccents("Renà©") `should be equal to` "Rena©"
    }

    @Test
    fun `the polish crossed L is stripped as well`() {
        Util.stripAccents("Łł") `should be equal to` "Ll"
    }

    @Test
    fun `a name without accents is left alone`() {
        Util.stripAccents("Angerfist") `should be equal to` "Angerfist"
    }

    @Test
    fun `ifNotNull runs the block only for a value`() {
        "Angerfist".ifNotNull { it.length } `should be equal to` 9
        (null as String?).ifNotNull { it.length }.`should be null`()
    }

    @Test
    fun `safeClose closes what it is given`() {
        var closed = false
        val closeable = Closeable { closed = true }

        closeable.safeClose()

        closed.`should be true`()
    }

    @Test
    fun `safeClose swallows a failing close`() {
        val closeable = Closeable { throw IOException("disk gone") }

        closeable.safeClose()
    }

    @Test
    fun `safeClose accepts nothing at all`() {
        (null as Closeable?).safeClose()
    }
}
