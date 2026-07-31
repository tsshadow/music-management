package org.moire.ultrasonic.log

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
}
