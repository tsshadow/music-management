/*
 * TrackDateFormatter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.util

/**
 * Formats the release date shown on a track row. Subsonic sends `date` as an ISO string, either
 * a plain `2024-03-12` or a full timestamp, and older servers send nothing but `year`.
 */
object TrackDateFormatter {

    private val ISO_DATE = Regex("""^(\d{4})-(\d{2})-(\d{2})""")

    /**
     * @return the date as `dd-MM-yyyy`, or the year on its own when there is no usable date,
     *         or null when the track carries neither.
     */
    fun format(date: String?, year: Int?): String? {
        val match = date?.let { ISO_DATE.find(it) }
        if (match != null) {
            val (isoYear, month, day) = match.destructured
            return "$day-$month-$isoYear"
        }
        if (year != null && year > 0) return year.toString()
        return null
    }
}
