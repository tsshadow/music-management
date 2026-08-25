/*
 * TrackInfoTarget.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

import java.io.Serializable

/**
 * Where a tap in the track info sheet wants to go.
 *
 * The sheet never navigates itself - it reports one of these back to whoever opened it, the
 * same way it reports menu actions and rating changes. Serializable because it travels in a
 * fragment result bundle.
 */
sealed class TrackInfoTarget : Serializable {

    /** One artist's own page. */
    data class Artist(val id: String, val name: String?) : TrackInfoTarget()

    /** Only the tracks every one of these artists is on. */
    data class Collaboration(val artistIds: List<String>, val title: String) : TrackInfoTarget()

    /**
     * Every track sharing one cluster value with this one. [filterName] is a server cluster type:
     * GENRE, YEAR, PUBLISHER or MOOD.
     */
    data class Facet(val filterName: String, val value: String) : TrackInfoTarget()

    companion object {
        @Suppress("unused")
        private const val serialVersionUID = 1L
    }
}
