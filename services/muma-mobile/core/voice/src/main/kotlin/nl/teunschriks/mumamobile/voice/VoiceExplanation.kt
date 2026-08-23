/*
 * VoiceExplanation.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

/**
 * @brief What a resolution says, in rows a screen can print.
 *
 * @details A resolved request ends up carrying a `Filters` object, and that object's `toString` is
 * the JSON the server wants: `[{"name":"GENRE","value":"hardstyle"}]`. Putting that in front of a
 * driver was the whole problem -- the one thing worth reading back is "genre Hardstyle", and that
 * is exactly what the JSON buries.
 *
 * The rows carry a [Field] rather than a label, because this module has no resources and the app
 * has nineteen languages. Every value that is a name -- a genre, a label, a year -- is already the
 * library's own spelling and is passed through unchanged. The one value that is a token rather
 * than a name is [Field.ORDER], and [Order] lists what it can be.
 */
object VoiceExplanation {

    enum class Field {
        /** The words the request arrived as. */
        HEARD,

        GENRE,
        LABEL,
        ARTIST,
        ALBUM,
        PLAYLIST,
        YEAR,

        /** The star range asked for, as "5", "4-5" or "4+". */
        RATING,

        /** Present only when the request asked for sets rather than tracks; the value is empty. */
        SETS,

        /** The order the tracks were asked in; the value is one of [Order]. */
        ORDER,

        /** The term the resolver could not place on its own, and is asking about. */
        QUESTION,

        /** Why nothing could be run, in the resolver's own words. */
        REASON
    }

    /** The tokens a [Field.ORDER] row can carry. */
    object Order {
        const val RELEASED = "released"
        const val ADDED = "added"
        const val RANDOM = "random"
    }

    data class Row(val field: Field, val value: String = "")

    /** The fields that name something, which is what a sentence about a request is built from. */
    private val NAMES = setOf(
        Field.GENRE,
        Field.LABEL,
        Field.ARTIST,
        Field.ALBUM,
        Field.PLAYLIST,
        Field.YEAR
    )

    /** Every row worth showing about [resolution], the words that were heard first. */
    fun of(resolution: QueryResolution): List<Row> {
        val rows = mutableListOf<Row>()
        resolution.trace.raw.takeIf { it.isNotBlank() }?.let { rows.add(Row(Field.HEARD, it)) }

        when (resolution) {
            is QueryResolution.Resolved -> rows.addAll(of(resolution.target))
            is QueryResolution.Ambiguous -> rows.add(Row(Field.QUESTION, resolution.term))
            is QueryResolution.NoMatch -> rows.add(Row(Field.REASON, resolution.reason))
        }

        return rows
    }

    /** Only the rows that say what will play. */
    fun of(target: Target): List<Row> = when (target) {
        is Target.Item -> listOf(Row(fieldOf(target.kind), target.name))
        is Target.Filtered -> filtered(target)
    }

    /**
     * The naming rows of [rows], in the order they were built.
     *
     * The status line says what is playing, not how it was sorted: "Playing genre Hardstyle" is a
     * sentence, "Playing genre Hardstyle, order newest release" is a log entry.
     */
    fun names(rows: List<Row>): List<Row> = rows.filter { it.field in NAMES }

    private fun filtered(target: Target.Filtered): List<Row> {
        val rows = mutableListOf<Row>()
        var ratingTag: String? = null

        target.filters.getAll().forEach { filter ->
            val value = display(filter.value)
            if (value.isEmpty()) return@forEach

            when (filter.name) {
                QueryResolver.FILTER_GENRE -> rows.add(Row(Field.GENRE, value))
                QueryResolver.FILTER_ARTIST -> rows.add(Row(Field.ARTIST, value))
                QueryResolver.FILTER_PUBLISHER -> rows.add(Row(Field.LABEL, value))
                QueryResolver.FILTER_YEAR -> rows.add(Row(Field.YEAR, value))
                QueryResolver.FILTER_LENGTH ->
                    if (value == VoiceQuery.LENGTH_LONG) rows.add(Row(Field.SETS))
                // The tag is only a fallback: the range is the wider truth, and the two are set
                // together for the same request.
                QueryResolver.FILTER_RATING -> ratingTag = value
                else -> Unit
            }
        }

        rating(target, ratingTag)?.let { rows.add(Row(Field.RATING, it)) }
        rows.add(Row(Field.ORDER, orderOf(target.sortMethod)))
        return rows
    }

    /**
     * A genre filter carries every spelling the library has of one genre, so the value is a list
     * far more often than it looks. Joining them is honest about that without being a JSON array.
     */
    private fun display(value: Any): String = when (value) {
        is String -> value.trim()
        is Collection<*> -> value.filterNotNull().joinToString(" / ") { it.toString() }
        else -> value.toString()
    }

    private fun rating(target: Target.Filtered, tag: String?): String? {
        val min = target.ratingMin
        val max = target.ratingMax
        return when {
            min != null && max != null && min == max -> "$min"
            min != null && max != null -> "$min-$max"
            min != null -> "$min+"
            max != null -> "-$max"
            else -> tag
        }
    }

    private fun orderOf(sortMethod: String): String = when (sortMethod) {
        SortMethods.ADDED -> Order.ADDED
        SortMethods.RANDOM -> Order.RANDOM
        else -> Order.RELEASED
    }

    private fun fieldOf(kind: EntityKind): Field = when (kind) {
        EntityKind.GENRE -> Field.GENRE
        EntityKind.LABEL -> Field.LABEL
        EntityKind.ARTIST -> Field.ARTIST
        EntityKind.ALBUM -> Field.ALBUM
        EntityKind.PLAYLIST -> Field.PLAYLIST
    }
}
