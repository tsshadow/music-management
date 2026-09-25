package nl.teunschriks.mumamobile.service

/**
 * One listen the app owes the server.
 *
 * Identified by the server, the track and the moment the play started ([key]). That triple is also
 * what the server stores the listen under: the start time travels as the Subsonic `time` parameter,
 * LMS records its own listen at exactly that second and relays the same second to MuMa, whose
 * `scrobble_listens` has a unique key on `(username, listened_at, track_id)`. Sending the same
 * entry twice -- a retry after a response that never arrived, a process that died between the send
 * and the removal -- therefore stores one listen, not two.
 *
 * @property open True while the play is still running in this process. An open entry is not sent:
 *  its playing time is still growing. A process that dies leaves it open, which is how the next
 *  process recognises it as finished (see [PendingScrobbleQueue.closeOrphans]).
 */
data class PendingScrobble(
    val trackId: String,
    val serverId: Int,
    val startedAtMs: Long,
    val playedSeconds: Long,
    val source: String,
    val open: Boolean,
    val attempts: Int = 0,
) {
    /** The identity of this play, and the server's de-duplication key for it. */
    val key: String get() = "$serverId|$trackId|$startedAtMs"
}

/** Where the queue keeps its entries between processes. */
interface PendingScrobbleStore {
    /** Everything stored, in the order it was saved. An unreadable store reads as empty. */
    fun load(): List<PendingScrobble>

    /** Replaces the stored entries. */
    fun save(entries: List<PendingScrobble>)
}

/**
 * A plain-text encoding of the queue: one entry per line, fields separated by a tab.
 *
 * Deliberately not Gson: R8 renames the fields of a data class in the release build, so a
 * reflection-based format written by one build is not guaranteed to be readable by the next -- and
 * the whole point of this queue is to survive into the next process, which after an update is the
 * next build. A line that does not parse is skipped rather than failing the whole queue.
 */
object PendingScrobbleCodec {
    private const val FIELD_COUNT = 7
    private const val SEPARATOR = "\t"

    /** Encodes [entries]; the inverse of [decode]. */
    fun encode(entries: List<PendingScrobble>): String = entries.joinToString("\n") {
        listOf(
            sanitize(it.trackId),
            it.serverId.toString(),
            it.startedAtMs.toString(),
            it.playedSeconds.toString(),
            sanitize(it.source),
            if (it.open) "1" else "0",
            it.attempts.toString()
        ).joinToString(SEPARATOR)
    }

    /** Decodes what [encode] wrote. Lines that do not parse are dropped. */
    fun decode(text: String?): List<PendingScrobble> {
        if (text.isNullOrBlank()) return emptyList()
        return text.lineSequence().mapNotNull(::decodeLine).toList()
    }

    private fun decodeLine(line: String): PendingScrobble? {
        val fields = line.split(SEPARATOR)
        if (fields.size != FIELD_COUNT || fields[0].isEmpty()) return null
        val serverId = fields[1].toIntOrNull()
        val startedAtMs = fields[2].toLongOrNull()
        val playedSeconds = fields[3].toLongOrNull()
        if (serverId == null || startedAtMs == null || playedSeconds == null) return null
        return PendingScrobble(
            trackId = fields[0],
            serverId = serverId,
            startedAtMs = startedAtMs,
            playedSeconds = playedSeconds,
            source = fields[4],
            open = fields[5] == "1",
            attempts = fields[6].toIntOrNull() ?: 0
        )
    }

    private fun sanitize(value: String) = value.replace('\t', ' ').replace('\n', ' ')
}

/**
 * The listens the app still has to deliver, kept in a [PendingScrobbleStore] so a failed send, a
 * phone without network or a killed process does not lose them.
 *
 * Every mutation is written through to the store at once. All methods are synchronized: the player
 * records from the main thread while the sender works from a background one.
 */
class PendingScrobbleQueue(
    private val store: PendingScrobbleStore,
    private val maxEntries: Int = MAX_ENTRIES,
    private val maxAgeMs: Long = MAX_AGE_MS,
) {
    private val entries: MutableList<PendingScrobble> = store.load().toMutableList()

    /** A copy of the queue, oldest first. */
    @Synchronized
    fun snapshot(): List<PendingScrobble> = entries.toList()

    /**
     * Adds [entry], or replaces the entry with the same [PendingScrobble.key]. A running play is
     * written again and again as its playing time grows; that is one listen, updated in place.
     * A replacement keeps the attempt count of what it replaces.
     */
    @Synchronized
    fun record(entry: PendingScrobble) {
        val index = entries.indexOfFirst { it.key == entry.key }
        if (index >= 0) {
            entries[index] = entry.copy(attempts = entries[index].attempts)
        } else {
            entries.add(entry)
            while (entries.size > maxEntries) entries.removeAt(0)
        }
        persist()
    }

    /**
     * Marks every open entry as finished. Called once when a new process starts: an entry that is
     * still open then belongs to a process that no longer exists, so its play is over and the
     * playing time last written is all there will ever be.
     *
     * @return How many entries were closed.
     */
    @Synchronized
    fun closeOrphans(): Int {
        var closed = 0
        entries.replaceAll { if (it.open) it.copy(open = false).also { closed++ } else it }
        if (closed > 0) persist()
        return closed
    }

    /**
     * The closed entries that may be sent to [activeServerId], oldest first.
     *
     * An entry recorded without a server (`serverId < 0`, a play in offline mode) goes to whichever
     * server is active. Entries older than the age limit are dropped here: a listen that could not
     * be delivered in that time is not going to be.
     */
    @Synchronized
    fun due(activeServerId: Int, nowMs: Long): List<PendingScrobble> {
        val before = entries.size
        entries.removeAll { nowMs - it.startedAtMs > maxAgeMs }
        if (entries.size != before) persist()
        return entries.filter { !it.open && (it.serverId < 0 || it.serverId == activeServerId) }
    }

    /** The server stored [entry]; forget it. */
    @Synchronized
    fun delivered(entry: PendingScrobble) {
        if (entries.removeAll { it.key == entry.key }) persist()
    }

    /** A send of [entry] failed and will be retried; counts the attempt. */
    @Synchronized
    fun failed(entry: PendingScrobble) {
        val index = entries.indexOfFirst { it.key == entry.key }
        if (index < 0) return
        entries[index] = entries[index].copy(attempts = entries[index].attempts + 1)
        persist()
    }

    private fun persist() = store.save(entries.toList())

    companion object {
        /** More listens than a fortnight offline produces; the oldest go first beyond it. */
        const val MAX_ENTRIES = 2000

        /** Thirty days. */
        const val MAX_AGE_MS = 30L * 24 * 60 * 60 * 1000
    }
}
