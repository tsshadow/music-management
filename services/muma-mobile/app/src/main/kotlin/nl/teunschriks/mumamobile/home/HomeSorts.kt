/*
 * HomeSorts.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * The server-side sorts behind the two home track lists.
 *
 * These are `TrackSortMethod` names the server parses by string (`Types.cpp`), not free text. They
 * live here rather than in the ViewModel because the "Show more" links have to open the full list
 * under the same sort the section was built with -- a section sorted one way and its own "show more"
 * sorted another is the kind of mismatch nobody notices until it is reported as a bug.
 */
object HomeSorts {

    /** Newest release date first: "Recently released". */
    const val RELEASED = "OriginalDateDescAndRelease"

    /** Most recently added to the library first: "Recently added". */
    const val ADDED = "AddedDesc"

    /** No order at all: what "speel willekeurig af" asks for. */
    const val RANDOM = "Random"
}
