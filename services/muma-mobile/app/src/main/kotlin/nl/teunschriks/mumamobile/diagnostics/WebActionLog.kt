/*
 * WebActionLog.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.diagnostics

/**
 * What the user did in the web interface, for a crash report.
 *
 * `nl.teunschriks.mumamobile.log.logAction` already does this for the Kotlin app, but it writes
 * into Timber and can only be read back as text. The `platform.diagnostics` contract in
 * `services/frontend/src/lib/platform/index.js` also wants `report()` to hand the list *back* --
 * the web player shows it on its diagnostics screen -- so the entries are kept as objects here
 * and rendered only when a report is built.
 *
 * Bounded at [MAX_ENTRIES] on purpose, and the bound is the contract's: "oldest first, at most
 * the last 50". A crash report has to be readable, and a screen that logs in a loop must not be
 * able to push the interesting lines out of the ring buffer on top of everything else.
 */
object WebActionLog {

    /** The contract's bound. Changing it is a change on both sides. */
    const val MAX_ENTRIES = 50

    /** Header the report uses, so the web actions are findable in a wall of log. */
    const val REPORT_HEADER = "--- Web UI actions ---"

    /**
     * @param action a short, stable name; the web side uses the same `subsystem.verb` shape the
     *   Kotlin app does.
     * @param at epoch milliseconds, as the contract's `at` field.
     * @param detail the JSON the caller passed, already serialised. Null when it passed none.
     */
    data class Entry(val action: String, val at: Long, val detail: String?)

    private val entries = ArrayDeque<Entry>()

    @Synchronized
    fun record(action: String, detail: String? = null, at: Long = System.currentTimeMillis()) {
        if (action.isBlank()) return
        entries.addLast(Entry(action, at, detail?.takeIf { it.isNotBlank() }))
        while (entries.size > MAX_ENTRIES) entries.removeFirst()
    }

    /** Oldest first. A copy, so a report being built cannot be mutated underneath it. */
    @Synchronized
    fun entries(): List<Entry> = entries.toList()

    @Synchronized
    fun clear() = entries.clear()

    /**
     * The log as it appears in a crash report, or an empty string when nothing was recorded --
     * a lone header in a report from a session that never opened the web UI would only be noise.
     */
    fun asReportText(): String {
        val snapshot = entries()
        if (snapshot.isEmpty()) return ""
        return buildString {
            append(REPORT_HEADER)
            append('\n')
            snapshot.forEach { entry ->
                append(entry.at)
                append(' ')
                append(entry.action)
                if (entry.detail != null) {
                    append(" | ")
                    append(entry.detail)
                }
                append('\n')
            }
        }
    }
}
