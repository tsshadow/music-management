/*
 * VoiceTraceLog.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import java.util.concurrent.ConcurrentLinkedDeque
import timber.log.Timber

/**
 * Keeps the last [CAPACITY] voice traces in memory and mirrors each one to Timber.
 *
 * The buffer, not the log file, is the sink that matters. File logging is opt-in and off by
 * default, Settings offers no way to share a log file -- only to list and delete them -- and the
 * trace worth having is the one from a drive nobody prepared for. `RingBufferLoggerTree` keeps the
 * general log the same way; this buffer is separate so that a busy playback session cannot push a
 * morning's voice traces out of it.
 */
object VoiceTraceLog {

    /** Enough for a drive's worth of requests without holding the library in memory twice. */
    const val CAPACITY = 50

    private val traces = ConcurrentLinkedDeque<QueryTrace>()

    fun record(trace: QueryTrace) {
        traces.addFirst(trace)
        while (traces.size > CAPACITY) traces.pollLast()
        Timber.i("voice trace\n%s", trace.render())
    }

    /** Newest first, which is the order the diagnostics screen shows them in. */
    fun recent(): List<QueryTrace> = traces.toList()

    fun clear() = traces.clear()
}
