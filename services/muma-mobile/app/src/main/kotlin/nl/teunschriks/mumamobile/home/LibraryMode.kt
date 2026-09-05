/*
 * LibraryMode.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * The songs / sets switch, as the browse pages see it.
 *
 * A "set" is a recording of ten minutes or more -- the threshold the switch queries on, and the
 * same one the tagger uses to decide whether a file gets a FESTIVAL or PODCAST tag at all.
 */
enum class LibraryMode {
    SONGS,
    SETS;

    companion object {
        /** Pages that answer on both sides of the switch. */
        val BOTH: Set<LibraryMode> = entries.toSet()

        fun of(isSetsMode: Boolean): LibraryMode = if (isSetsMode) SETS else SONGS
    }
}
