package nl.teunschriks.mumamobile.capacitor

import androidx.media3.common.Player
import nl.teunschriks.mumamobile.service.DownloadState
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * The parts of the Capacitor bridge that are a translation and nothing else.
 *
 * Every one of these is a contract with `services/frontend/src/lib/platform/index.js`: the status
 * words, the download states, the two server bases and the order of a queue. They are pure
 * functions precisely so that the contract can be checked without a player, a WebView or a
 * device -- the plugins around them are thin enough that if these are right, the marshalling is
 * the only thing left to get wrong.
 */
class CapacitorContractTest {

    // ------------------------------------------------------------ player status

    @Test
    fun `a ready player that is playing is playing`() {
        playerStatusOf(Player.STATE_READY, isPlaying = true) shouldBeEqualTo PlayerStatus.PLAYING
    }

    @Test
    fun `a ready player that is not playing is paused, not idle`() {
        playerStatusOf(Player.STATE_READY, isPlaying = false) shouldBeEqualTo PlayerStatus.PAUSED
    }

    @Test
    fun `buffering is loading`() {
        playerStatusOf(Player.STATE_BUFFERING, isPlaying = false) shouldBeEqualTo PlayerStatus.LOADING
    }

    @Test
    fun `the end of the queue is ended`() {
        playerStatusOf(Player.STATE_ENDED, isPlaying = false) shouldBeEqualTo PlayerStatus.ENDED
    }

    @Test
    fun `an idle player is idle`() {
        playerStatusOf(Player.STATE_IDLE, isPlaying = false) shouldBeEqualTo PlayerStatus.IDLE
    }

    /**
     * `MediaPlayerManager.playbackState` answers 0 while no controller is connected, which is not
     * one of Media3's states. It has to read as "nothing loaded" rather than fall off the mapping.
     */
    @Test
    fun `no controller at all is idle`() {
        playerStatusOf(0, isPlaying = false) shouldBeEqualTo PlayerStatus.IDLE
    }

    /** A failed item leaves Media3 in STATE_IDLE, so only the flag can tell the two apart. */
    @Test
    fun `a failure outranks every state`() {
        playerStatusOf(Player.STATE_IDLE, isPlaying = false, failed = true) shouldBeEqualTo PlayerStatus.ERROR
        playerStatusOf(Player.STATE_READY, isPlaying = true, failed = true) shouldBeEqualTo PlayerStatus.ERROR
    }

    @Test
    fun `the wire words are the ones the contract lists`() {
        PlayerStatus.entries.map { it.wire } shouldBeEqualTo
            listOf("idle", "loading", "playing", "paused", "ended", "error")
    }

    // -------------------------------------------------------------- repeat mode

    @Test
    fun `every wire word becomes its Media3 repeat mode`() {
        repeatModeOf("all") shouldBeEqualTo Player.REPEAT_MODE_ALL
        repeatModeOf("one") shouldBeEqualTo Player.REPEAT_MODE_ONE
        repeatModeOf("none") shouldBeEqualTo Player.REPEAT_MODE_OFF
    }

    /** A `setMode` call that left the field out means the same as "none" everywhere else here. */
    @Test
    fun `an unknown or missing repeat word is off, not a crash`() {
        repeatModeOf(null) shouldBeEqualTo Player.REPEAT_MODE_OFF
        repeatModeOf("shuffle") shouldBeEqualTo Player.REPEAT_MODE_OFF
    }

    @Test
    fun `every Media3 repeat mode becomes its wire word`() {
        repeatModeWire(Player.REPEAT_MODE_ALL) shouldBeEqualTo "all"
        repeatModeWire(Player.REPEAT_MODE_ONE) shouldBeEqualTo "one"
        repeatModeWire(Player.REPEAT_MODE_OFF) shouldBeEqualTo "none"
    }

    @Test
    fun `the mapping is a round trip in both directions`() {
        listOf("none", "all", "one").forEach { wire ->
            repeatModeWire(repeatModeOf(wire)) shouldBeEqualTo wire
        }
    }

    // ---------------------------------------------------------- download states

    @Test
    fun `every download state maps onto one of the five the contract knows`() {
        val allowed = setOf("none", "queued", "running", "done", "failed")
        DownloadState.entries.forEach { state ->
            (downloadStateWire(state) in allowed) shouldBeEqualTo true
        }
    }

    @Test
    fun `a pinned track reads as downloaded and a retry as still running`() {
        downloadStateWire(DownloadState.PINNED) shouldBeEqualTo "done"
        downloadStateWire(DownloadState.DONE) shouldBeEqualTo "done"
        downloadStateWire(DownloadState.RETRYING) shouldBeEqualTo "running"
        downloadStateWire(DownloadState.DOWNLOADING) shouldBeEqualTo "running"
        downloadStateWire(DownloadState.QUEUED) shouldBeEqualTo "queued"
        downloadStateWire(DownloadState.FAILED) shouldBeEqualTo "failed"
        downloadStateWire(DownloadState.CANCELLED) shouldBeEqualTo "failed"
        downloadStateWire(DownloadState.IDLE) shouldBeEqualTo "none"
        downloadStateWire(DownloadState.UNKNOWN) shouldBeEqualTo "none"
    }

    // --------------------------------------------------------------- serverUrl

    @Test
    fun `serverUrl derives the muma base from the subsonic base`() {
        val urls = serverUrlsOf("https://lms.example.org")
        urls.subsonic shouldBeEqualTo "https://lms.example.org"
        urls.mumaApi shouldBeEqualTo "https://lms.example.org/muma"
    }

    /** The web side concatenates; a trailing slash on either base is a doubled slash and a 404. */
    @Test
    fun `serverUrl never ends in a slash`() {
        val urls = serverUrlsOf("https://lms.example.org/")
        urls.subsonic shouldBeEqualTo "https://lms.example.org"
        urls.mumaApi shouldBeEqualTo "https://lms.example.org/muma"
    }

    /** The production host has muma on its own name, and the shell must agree with the client. */
    @Test
    fun `serverUrl follows the production exception`() {
        serverUrlsOf("https://lms.example.com").mumaApi shouldBeEqualTo "https://muma.example.com"
    }

    // ------------------------------------------------------------ queue indices

    @Test
    fun `an index past the end starts at the last track rather than refusing`() {
        clampQueueIndex(9, 3) shouldBeEqualTo 2
        clampQueueIndex(-4, 3) shouldBeEqualTo 0
        clampQueueIndex(1, 3) shouldBeEqualTo 1
    }

    @Test
    fun `an empty queue starts at zero`() {
        clampQueueIndex(5, 0) shouldBeEqualTo 0
    }

    // -------------------------------------------------------------- equalizer

    /** Ten web bands onto five native ones: the shape survives, the ends stay the ends. */
    @Test
    fun `the web curve is resampled onto the bands the device has`() {
        val gains = listOf(-10f, -8f, -6f, -4f, -2f, 2f, 4f, 6f, 8f, 10f)
        val levels = nativeBandGains(gains, preamp = 0f, bandCount = 5, minMillibels = -1500, maxMillibels = 1500)

        levels.size shouldBeEqualTo 5
        levels.first() shouldBeEqualTo (-1000).toShort()
        levels.last() shouldBeEqualTo 1000.toShort()
    }

    @Test
    fun `the preamp is folded into every band`() {
        val levels = nativeBandGains(listOf(0f, 0f), preamp = 3f, bandCount = 2, minMillibels = -1500, maxMillibels = 1500)
        levels.toList() shouldBeEqualTo listOf<Short>(300, 300)
    }

    @Test
    fun `a curve that runs out of headroom is clamped to what the device allows`() {
        val levels = nativeBandGains(listOf(40f), preamp = 20f, bandCount = 3, minMillibels = -1500, maxMillibels = 1500)
        levels.toList() shouldBeEqualTo listOf<Short>(1500, 1500, 1500)
    }

    @Test
    fun `a device without bands gets nothing rather than an exception`() {
        nativeBandGains(listOf(1f), 0f, 0, -1500, 1500).size shouldBeEqualTo 0
    }
}
