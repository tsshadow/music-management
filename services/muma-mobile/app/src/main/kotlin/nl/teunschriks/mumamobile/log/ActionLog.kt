/*
 * ActionLog.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.log

import timber.log.Timber

/**
 * One shape for "this is what happened", so a diagnostics report reads as a sequence of actions
 * rather than as whatever each screen felt like printing.
 *
 * Reports used to be dominated by lifecycle noise, and the thing the user had actually done was
 * either unlogged or indistinguishable from it. Every line written through here starts with
 * [ACTION_PREFIX] and a dotted name, so a report can be skimmed for the ten lines that matter and
 * grepped for one subsystem.
 *
 * Names are `subsystem.verb`: `player.play`, `list.load`, `rating.set`. The verb is what was asked
 * for, not what came back -- an action followed by no result line is itself the finding.
 */
const val ACTION_PREFIX = "action"

/**
 * `action player.play | index=3 | queue=100`
 *
 * Details with a null value are left out: a report is read by a human, and `index=null` costs a
 * line's width to say nothing.
 */
internal fun formatAction(name: String, details: List<Pair<String, Any?>>): String {
    val shown = details.filter { it.second != null }
    if (shown.isEmpty()) return "$ACTION_PREFIX $name"
    return shown.joinToString(
        separator = " | ",
        prefix = "$ACTION_PREFIX $name | "
    ) { "${it.first}=${it.second}" }
}

/** Records a user-visible action. Never throws: logging must not be able to break the app. */
fun logAction(name: String, vararg details: Pair<String, Any?>) {
    try {
        Timber.i(formatAction(name, details.toList()))
    } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
        // A report that is missing a line is better than an app that fell over writing one.
    }
}
