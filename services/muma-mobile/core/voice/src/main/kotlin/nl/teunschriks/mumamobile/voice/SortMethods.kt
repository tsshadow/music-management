/*
 * SortMethods.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * The `sortMethod` values the server accepts on `getSongs`.
 *
 * `StarredDateDesc` is advertised by `getSongSortMethods` but errors on this query path, so no
 * spoken phrase maps to it and it is deliberately absent here.
 */
object SortMethods {

    /** Newest release date first: "Recent uitgebracht". */
    const val RELEASED = "OriginalDateDescAndRelease"

    /** Most recently added to the library first: "Recent toegevoegd". */
    const val ADDED = "AddedDesc"

    /** No order at all: what "speel willekeurig af" asks for. */
    const val RANDOM = "Random"
}
