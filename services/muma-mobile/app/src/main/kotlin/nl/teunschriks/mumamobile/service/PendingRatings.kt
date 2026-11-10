package nl.teunschriks.mumamobile.service

/**
 * One rating the app still owes the server.
 *
 * A track has at most one: a newer rating of the same track on the same server replaces the
 * older one, so the last rating wins and the server never sees the ones in between. Sending the
 * same entry twice is harmless, because `setRating` stores a value, not a change.
 *
 * @property trackId the track.
 * @property serverId the server the rating belongs to; `-1` (the offline library was active)
 *   goes to whichever server is active next.
 * @property rating 0 to 5; 0 clears the rating, 5 is a favorite.
 * @property ratedAtMs when the listener gave it; tells two ratings of one track apart.
 * @property attempts sends that failed and will be retried.
 */
data class PendingRating(
    val trackId: String,
    val serverId: Int,
    val rating: Int,
    val ratedAtMs: Long,
    val attempts: Int = 0,
) {
    /** One entry per track per server. */
    val key: String get() = "$serverId|$trackId"
}

/** Where the rating queue keeps its entries between processes. */
interface PendingRatingStore {
    /** Everything stored, in the order it was saved. An unreadable store reads as empty. */
    fun load(): List<PendingRating>

    /** Replaces the stored entries. */
    fun save(entries: List<PendingRating>)
}

/** A [PendingRatingStore] in memory, for the tests and as a fallback. */
class InMemoryRatingStore(initial: List<PendingRating> = emptyList()) : PendingRatingStore {
    private var entries = initial

    override fun load(): List<PendingRating> = entries

    override fun save(entries: List<PendingRating>) {
        this.entries = entries
    }
}

/**
 * A plain-text encoding of the rating queue: one entry per line, fields separated by a tab. Not
 * Gson, for the reason [PendingScrobbleCodec] gives: R8 renames fields between builds, and this
 * queue has to be readable by the next build.
 */
object PendingRatingCodec {
    private const val FIELD_COUNT = 5
    private const val SEPARATOR = "\t"

    /** Encodes [entries]; the inverse of [decode]. */
    fun encode(entries: List<PendingRating>): String = entries.joinToString("\n") {
        listOf(
            it.trackId.replace('\t', ' ').replace('\n', ' '),
            it.serverId.toString(),
            it.rating.toString(),
            it.ratedAtMs.toString(),
            it.attempts.toString()
        ).joinToString(SEPARATOR)
    }

    /** Decodes what [encode] wrote. Lines that do not parse are dropped. */
    fun decode(text: String?): List<PendingRating> {
        if (text.isNullOrBlank()) return emptyList()
        return text.lineSequence().mapNotNull(::decodeLine).toList()
    }

    private fun decodeLine(line: String): PendingRating? {
        val fields = line.split(SEPARATOR)
        if (fields.size != FIELD_COUNT || fields[0].isEmpty()) return null
        val serverId = fields[1].toIntOrNull()
        val rating = fields[2].toIntOrNull()
        val ratedAtMs = fields[3].toLongOrNull()
        if (serverId == null || rating == null || ratedAtMs == null) return null
        return PendingRating(fields[0], serverId, rating, ratedAtMs, fields[4].toIntOrNull() ?: 0)
    }
}

/**
 * The ratings the app still has to deliver, kept in a [PendingRatingStore] so a server that is
 * down, a phone without network or a killed process does not lose them
 * (docs/designs/offline-followups/).
 *
 * Every change is written to the store at once. All methods are synchronized: ratings arrive on
 * the main thread and from the car while the sender works on a background thread.
 */
class PendingRatingQueue(
    private val store: PendingRatingStore,
    private val maxEntries: Int = MAX_ENTRIES,
    private val maxAgeMs: Long = MAX_AGE_MS,
) {
    private val entries: MutableList<PendingRating> = store.load().toMutableList()

    /** A copy of the queue, oldest first. */
    @Synchronized
    fun snapshot(): List<PendingRating> = entries.toList()

    /** Whether nothing waits. */
    @Synchronized
    fun isEmpty(): Boolean = entries.isEmpty()

    /**
     * Adds [entry]. An older entry for the same track and server goes: the last rating wins. The
     * new entry moves to the end of the queue, so ratings go out in the order they were given.
     */
    @Synchronized
    fun record(entry: PendingRating) {
        entries.removeAll { it.key == entry.key }
        entries.add(entry)
        while (entries.size > maxEntries) entries.removeAt(0)
        persist()
    }

    /**
     * The entries that may be sent to [activeServerId], oldest first. An entry without a server
     * (`serverId < 0`) goes to whichever server is active. Entries older than the age limit are
     * dropped here.
     */
    @Synchronized
    fun due(activeServerId: Int, nowMs: Long): List<PendingRating> {
        val before = entries.size
        entries.removeAll { nowMs - it.ratedAtMs > maxAgeMs }
        if (entries.size != before) persist()
        return entries.filter { it.serverId < 0 || it.serverId == activeServerId }
    }

    /**
     * The server stored [entry], or will never take it. Removed only while it is still the
     * newest rating of its track: a rating given during the send stays and goes out next.
     */
    @Synchronized
    fun done(entry: PendingRating) {
        if (entries.removeAll { it.key == entry.key && it.ratedAtMs == entry.ratedAtMs && it.rating == entry.rating }) persist()
    }

    /** A send of [entry] failed and will be retried; counts the attempt. */
    @Synchronized
    fun failed(entry: PendingRating) {
        val index = entries.indexOfFirst { it.key == entry.key && it.ratedAtMs == entry.ratedAtMs }
        if (index < 0) return
        entries[index] = entries[index].copy(attempts = entries[index].attempts + 1)
        persist()
    }

    private fun persist() = store.save(entries.toList())

    companion object {
        /** Far more tracks than anyone rates while offline; the oldest go first beyond it. */
        const val MAX_ENTRIES = 5000

        /** Thirty days, the same limit as the scrobble queue. */
        const val MAX_AGE_MS = 30L * 24 * 60 * 60 * 1000
    }
}

/**
 * Sends the queue's due entries, oldest first, and keeps what could not be sent.
 *
 * @param send delivers one entry; an exception is judged by [ScrobbleDelivery.outcomeOf], the same
 *   rule the scrobble queue uses: only "no such track" and "missing parameter" are final.
 */
class RatingDelivery(
    private val queue: PendingRatingQueue,
    private val activeServerId: () -> Int,
    private val nowMs: () -> Long,
    private val send: (PendingRating) -> Unit,
) {
    /**
     * One pass over the queue. Stops at the first entry that has to be retried: when one send
     * fails for want of a server, the next one will too.
     *
     * @param onResult called once per entry tried, with true when the server stored it.
     * @return true when entries are left that a later pass should retry.
     */
    fun flush(onResult: (PendingRating, Boolean) -> Unit = { _, _ -> }): Boolean {
        for (entry in queue.due(activeServerId(), nowMs())) {
            val outcome = try {
                send(entry)
                ScrobbleOutcome.DELIVERED
            } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
                ScrobbleDelivery.outcomeOf(failure)
            }
            when (outcome) {
                ScrobbleOutcome.DELIVERED, ScrobbleOutcome.REJECTED -> {
                    queue.done(entry)
                    onResult(entry, outcome == ScrobbleOutcome.DELIVERED)
                }
                ScrobbleOutcome.RETRY -> {
                    queue.failed(entry)
                    onResult(entry, false)
                    return true
                }
            }
        }
        return false
    }
}
