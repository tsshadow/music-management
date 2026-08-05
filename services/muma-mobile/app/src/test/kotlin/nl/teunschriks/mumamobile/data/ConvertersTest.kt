package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * The string list converter used to build its type via an anonymous Guava TypeToken subclass,
 * which R8 full mode strips in release builds ("TypeCapture isn't parameterized"). These tests
 * pin the round trip so a future rewrite cannot silently change the stored representation.
 */
class ConvertersTest {

    private val converters = Converters()

    @Test
    fun `should round trip a list of strings`() {
        val input = listOf("Rock", "Post-Punk", "Ambient")

        val json = converters.fromStringList(input)
        val output = converters.toStringList(json)

        output shouldBeEqualTo input
    }

    @Test
    fun `should round trip strings needing escaping`() {
        val input = listOf("Drum & Bass", "R\"n\"B", "Hip/Hop", "")

        val output = converters.toStringList(converters.fromStringList(input))

        output shouldBeEqualTo input
    }

    @Test
    fun `should round trip an empty list`() {
        converters.toStringList(converters.fromStringList(emptyList())) shouldBeEqualTo emptyList()
    }

    @Test
    fun `should read the json representation written by the previous implementation`() {
        converters.toStringList("[\"Jazz\",\"Fusion\"]") shouldBeEqualTo listOf("Jazz", "Fusion")
    }

    @Test
    fun `should return null for a null column value`() {
        converters.toStringList(null) shouldBeEqualTo null
    }

    @Test
    fun `should return null for a json null`() {
        converters.toStringList(converters.fromStringList(null)) shouldBeEqualTo null
    }
}
