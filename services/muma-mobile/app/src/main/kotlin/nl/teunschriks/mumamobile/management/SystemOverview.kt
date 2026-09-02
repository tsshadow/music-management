/*
 * SystemOverview.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import nl.teunschriks.mumamobile.api.muma.MumaActivity
import nl.teunschriks.mumamobile.api.muma.MumaActivityEntry
import nl.teunschriks.mumamobile.api.muma.MumaContainer
import nl.teunschriks.mumamobile.api.muma.MumaVersions

/**
 * The levels `/api/events` accepts, in the server's order.
 *
 * `list_events` answers 400 for a level it does not know, so a chip the app invented would take the
 * whole page down rather than filter it. `EventLevelsTest` compares this list against the server's
 * own constant.
 */
val EVENT_LEVELS = listOf("INFO", "WARNING", "ERROR", "CRITICAL")

/** Docker's word for a container that is up. */
private const val RUNNING = "running"

/** What the overview page says, boiled down from the three calls behind it. */
data class SystemOverview(
    val running: Int,
    val total: Int,
    val offline: List<String>,
    val version: String?,
    val lastAdded: MumaActivityEntry?
) {
    /**
     * True only when there is something to be healthy about. The web reads the same thing as
     * `containers.every(...)`, which is true for an empty list and puts a green tick on a call that
     * answered nothing -- and an answer of zero containers means the call failed or docker is
     * unreachable, which is the opposite of healthy.
     */
    val allRunning: Boolean get() = total > 0 && offline.isEmpty()
}

fun summarizeSystem(
    containers: List<MumaContainer>,
    activity: MumaActivity?,
    versions: MumaVersions?
): SystemOverview = SystemOverview(
    running = containers.count { it.status.equals(RUNNING, ignoreCase = true) },
    total = containers.size,
    offline = containers.filterNot { it.status.equals(RUNNING, ignoreCase = true) }.map { it.name },
    version = versions?.musicManager,
    lastAdded = activity?.recentAdded?.firstOrNull()
)
