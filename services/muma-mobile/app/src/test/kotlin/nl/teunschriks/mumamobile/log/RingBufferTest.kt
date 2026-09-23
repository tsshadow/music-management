package nl.teunschriks.mumamobile.log

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

class RingBufferTest {

    @Test
    fun `keeps all lines while under the cap`() {
        val buffer = RingBuffer(maxLines = 3)

        buffer.append("one")
        buffer.append("two")
        val result = buffer.append("three")

        result shouldBeEqualTo listOf("one", "two", "three")
    }

    @Test
    fun `drops the oldest line once the cap is exceeded`() {
        val buffer = RingBuffer(maxLines = 3)

        buffer.append("one")
        buffer.append("two")
        buffer.append("three")
        val result = buffer.append("four")

        result shouldBeEqualTo listOf("two", "three", "four")
    }

    @Test
    fun `clear empties the buffer`() {
        val buffer = RingBuffer(maxLines = 3)
        buffer.append("one")

        buffer.clear()

        buffer.snapshot() shouldBeEqualTo emptyList()
    }

    @Test
    fun `a repeat inside the window is held back`() {
        val gate = RepeatGate(windowMillis = 1_000)

        gate.admit("W/GenreTintCache/Could not read", now = 0) shouldBeEqualTo 0
        gate.admit("W/GenreTintCache/Could not read", now = 10) shouldBeEqualTo null
        gate.admit("W/GenreTintCache/Could not read", now = 999) shouldBeEqualTo null
    }

    @Test
    fun `the first line after the window says how many were held back`() {
        val gate = RepeatGate(windowMillis = 1_000)
        gate.admit("key", now = 0)
        repeat(265) { gate.admit("key", now = 1L + it) }

        gate.admit("key", now = 1_000) shouldBeEqualTo 265
    }

    @Test
    fun `different lines do not hold each other back`() {
        val gate = RepeatGate(windowMillis = 1_000)
        gate.admit("one", now = 0)

        gate.admit("two", now = 1) shouldBeEqualTo 0
    }

    @Test
    fun `a long stack trace is cut to its top`() {
        val message = (1..40).joinToString("\n") { "line $it" }

        val capped = RingBufferLoggerTree.capLines(message).lines()

        capped.size shouldBeEqualTo RingBufferLoggerTree.MAX_MESSAGE_LINES + 1
        capped.first() shouldBeEqualTo "line 1"
        capped.last() shouldBeEqualTo "\t... 28 more lines"
    }

    @Test
    fun `a short message is kept whole`() {
        RingBufferLoggerTree.capLines("one\ntwo") shouldBeEqualTo "one\ntwo"
    }
}
