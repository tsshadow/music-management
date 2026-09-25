package nl.teunschriks.mumamobile.service

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/** The on-disk form of the scrobble queue, which has to be readable by the next build. */
class PendingScrobbleCodecTest {

    @Test
    fun `entries survive a round trip`() {
        val entries = listOf(
            PendingScrobble("9596523", 0, 1_758_778_000_000, 612, "auto", open = true, attempts = 0),
            PendingScrobble("9648936", -1, 1_758_778_700_000, 5, "mobile", open = false, attempts = 3)
        )

        PendingScrobbleCodec.decode(PendingScrobbleCodec.encode(entries)) `should be equal to` entries
    }

    @Test
    fun `an empty or missing store reads as an empty queue`() {
        PendingScrobbleCodec.decode(null) `should be equal to` emptyList()
        PendingScrobbleCodec.decode("") `should be equal to` emptyList()
    }

    @Test
    fun `a damaged line is skipped, the rest is kept`() {
        val good = PendingScrobble("1", 0, 10, 20, "mobile", open = false)
        val text = "garbage\n" + PendingScrobbleCodec.encode(listOf(good)) + "\nx\t0\tnot-a-number\t1\tmobile\t0\t0"

        PendingScrobbleCodec.decode(text) `should be equal to` listOf(good)
    }
}
