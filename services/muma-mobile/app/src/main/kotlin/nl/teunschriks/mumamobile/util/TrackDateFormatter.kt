/*
 * TrackDateFormatter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

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

    /**
     * Which of a server's two dates to treat as the release date.
     *
     * MuMa resolves a release date into `ORIGINALDATE`, which LMS sends as `originalDate`, while
     * `date` stays this edition's. The original is the more meaningful one, but only when it is at
     * least as precise: a bare `2024` must not throw away a full date the server did send.
     *
     * The app displays one release date, so the choice is made here at the API boundary rather than
     * carried through the domain model and every view that shows it.
     */
    fun preferredReleaseDate(date: String?, originalDate: String?): String? {
        val preferred = if (precision(originalDate) >= precision(date)) originalDate else date
        return preferred?.takeIf { it.isNotBlank() } ?: date
    }

    private fun precision(value: String?): Int = value?.count { it.isDigit() } ?: 0
}
