package nl.teunschriks.mumamobile.service

import java.io.IOException
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError
import nl.teunschriks.mumamobile.api.subsonic.SubsonicRESTException
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The scrobble decision end to end, without a player: which plays become listens, what survives a
 * process that dies, and what a failed or repeated send does. Bug report 071.
 */
class ScrobbleLedgerTest {

    /** A store that outlives the queue built on it -- the stand-in for a new process. */
    private class MemoryStore : PendingScrobbleStore {
        var saved: List<PendingScrobble> = emptyList()
        override fun load() = saved
        override fun save(entries: List<PendingScrobble>) {
            saved = entries
        }
    }

    private var wall = START_WALL
    private var elapsed = 0L
    private val store = MemoryStore()
    private var queue = PendingScrobbleQueue(store)
    private var ledger = ScrobbleLedger(queue, PlayTally({ wall }, { elapsed }))

    /** What the "server" received, as (track, start time) pairs. */
    private val sent = mutableListOf<PendingScrobble>()
    private var failWith: Exception? = null

    private fun delivery() = ScrobbleDelivery(queue, activeServerId = { SERVER }, nowMs = { wall }) { entry ->
        failWith?.let { throw it }
        sent.add(entry)
    }

    private fun play(seconds: Long) {
        elapsed += seconds * 1000
        wall += seconds * 1000
    }

    /** Throws the in-memory state away and starts again from the store, as a new process does. */
    private fun restartProcess() {
        queue = PendingScrobbleQueue(store)
        ledger = ScrobbleLedger(queue, PlayTally({ wall }, { elapsed }))
        queue.closeOrphans()
    }

    @Test
    fun `a play past the threshold that is then skipped is a listen, dated at its start`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(30)
        ledger.onTrack("t2", SERVER, "mobile", playing = true)

        delivery().flush() `should be equal to` false

        sent.size `should be equal to` 1
        sent[0].trackId `should be equal to` "t1"
        sent[0].startedAtMs `should be equal to` START_WALL
        sent[0].playedSeconds `should be equal to` 30L
        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `a play below the threshold is not a listen`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(4)
        ledger.onTrack("t2", SERVER, "mobile", playing = true)

        delivery().flush()

        sent.size `should be equal to` 0
        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `a running play is kept on disk but not sent until it is over`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(60)
        ledger.checkpoint()

        delivery().flush()

        sent.size `should be equal to` 0
        store.saved.single().open `should be equal to` true
        store.saved.single().playedSeconds `should be equal to` 60L
    }

    @Test
    fun `a play whose process died is sent by the next process, exactly once`() {
        ledger.onTrack("t1", SERVER, "auto", playing = true)
        play(600)
        ledger.checkpoint()
        // The process is killed here: nothing closes the play.

        restartProcess()
        delivery().flush()
        delivery().flush()

        sent.size `should be equal to` 1
        sent[0].trackId `should be equal to` "t1"
        sent[0].playedSeconds `should be equal to` 600L
        sent[0].source `should be equal to` "auto"
        store.saved.size `should be equal to` 0
    }

    @Test
    fun `a pending listen from before a restart is sent once, with the same key`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(20)
        ledger.onTrack(null, SERVER, "mobile", playing = false)
        // Closed and on disk, but the process died before it could be sent.

        restartProcess()
        delivery().flush()

        sent.map { it.key } `should be equal to` listOf("$SERVER|t1|$START_WALL")
    }

    @Test
    fun `offline, a listen is queued and sent when the network returns`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(45)
        ledger.onTrack("t2", SERVER, "mobile", playing = true)
        play(45)
        ledger.onTrack(null, SERVER, "mobile", playing = false)

        failWith = OfflineException("no network")
        delivery().flush() `should be equal to` true
        failWith = IOException("timeout")
        delivery().flush() `should be equal to` true

        sent.size `should be equal to` 0
        queue.snapshot().map { it.trackId } `should be equal to` listOf("t1", "t2")
        queue.snapshot()[0].attempts `should be equal to` 2

        failWith = null
        delivery().flush() `should be equal to` false

        sent.map { it.trackId } `should be equal to` listOf("t1", "t2")
        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `a track the server does not know is dropped instead of retried forever`() {
        ledger.onTrack("gone", SERVER, "mobile", playing = true)
        play(10)
        ledger.onTrack(null, SERVER, "mobile", playing = false)

        failWith = SubsonicRESTException(SubsonicError.RequestedDataWasNotFound)
        delivery().flush() `should be equal to` false

        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `a server error is retried`() {
        ScrobbleDelivery.outcomeOf(SubsonicRESTException(SubsonicError.Generic("boom"))) `should be equal to` ScrobbleOutcome.RETRY
        ScrobbleDelivery.outcomeOf(IllegalStateException("HTTP 500")) `should be equal to` ScrobbleOutcome.RETRY
        ScrobbleDelivery.outcomeOf(SubsonicRESTException(SubsonicError.RequiredParamMissing)) `should be equal to` ScrobbleOutcome.REJECTED
    }

    /**
     * Bug report 095: rapid taps on "next" pass the player through several items within
     * milliseconds -- and before the fix, a UI and service correcting each other flipped between two
     * of them for as long as it lasted. Only what was actually listened to is a listen, once.
     */
    @Test
    fun `a burst of quick skips records only the items that were actually played, once each`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(40)
        for (id in listOf("t2", "t3", "t2", "t3")) {
            ledger.onTrack(id, SERVER, "mobile", playing = true)
            elapsed += 80
            wall += 80
        }
        play(60)
        ledger.onTrack("t4", SERVER, "mobile", playing = true)

        delivery().flush()

        sent.map { it.trackId } `should be equal to` listOf("t1", "t3")
        sent[1].playedSeconds `should be equal to` 60L
        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `the same track played twice in a row is two listens`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(30)
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(30)
        ledger.onTrack(null, SERVER, "mobile", playing = false)

        delivery().flush()

        sent.map { it.trackId } `should be equal to` listOf("t1", "t1")
        sent[1].startedAtMs `should be equal to` START_WALL + 30_000
    }

    @Test
    fun `paused time is not played time, and a paused-on track starts when play is pressed`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = false)
        play(3600) // A restored queue, sitting paused for an hour.
        ledger.onPlaying(true)
        play(10)
        ledger.onPlaying(false)
        play(300)
        ledger.onPlaying(true)
        play(10)
        ledger.onEnded()

        delivery().flush()

        sent.single().playedSeconds `should be equal to` 20L
        sent.single().startedAtMs `should be equal to` START_WALL + 3_600_000
    }

    @Test
    fun `the end of the queue closes the last play`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(200)
        ledger.onEnded()

        delivery().flush()

        sent.single().trackId `should be equal to` "t1"
        ledger.hasTrack `should be equal to` false
    }

    @Test
    fun `a track loaded but never played is nothing`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = false)
        play(100)
        ledger.onTrack("t2", SERVER, "mobile", playing = false)

        delivery().flush()

        sent.size `should be equal to` 0
    }

    @Test
    fun `a checkpoint and the close of the same play are one entry`() {
        ledger.onTrack("t1", SERVER, "mobile", playing = true)
        play(10)
        ledger.checkpoint()
        play(10)
        ledger.checkpoint()
        play(10)
        ledger.onTrack(null, SERVER, "mobile", playing = false)

        queue.snapshot().size `should be equal to` 1
        queue.snapshot().single().playedSeconds `should be equal to` 30L
        queue.snapshot().single().open `should be equal to` false
    }

    @Test
    fun `listens for another server wait, listens without one go to the active server`() {
        queue.record(PendingScrobble("a", 7, START_WALL, 10, "mobile", open = false))
        queue.record(PendingScrobble("b", -1, START_WALL + 1, 10, "mobile", open = false))
        queue.record(PendingScrobble("c", SERVER, START_WALL + 2, 10, "mobile", open = false))

        delivery().flush()

        sent.map { it.trackId } `should be equal to` listOf("b", "c")
        queue.snapshot().map { it.trackId } `should be equal to` listOf("a")
    }

    @Test
    fun `a listen older than the age limit is given up`() {
        queue.record(PendingScrobble("old", SERVER, START_WALL, 10, "mobile", open = false))
        wall += PendingScrobbleQueue.MAX_AGE_MS + 1

        delivery().flush()

        sent.size `should be equal to` 0
        queue.snapshot().size `should be equal to` 0
    }

    @Test
    fun `the queue is capped, oldest first`() {
        val small = PendingScrobbleQueue(MemoryStore(), maxEntries = 2)
        small.record(PendingScrobble("a", SERVER, 1, 10, "mobile", open = false))
        small.record(PendingScrobble("b", SERVER, 2, 10, "mobile", open = false))
        small.record(PendingScrobble("c", SERVER, 3, 10, "mobile", open = false))

        small.snapshot().map { it.trackId } `should be equal to` listOf("b", "c")
    }

    private companion object {
        const val SERVER = 0
        const val START_WALL = 1_758_000_000_000L
    }
}
