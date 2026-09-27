/*
 * BrowseQuery.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.api.subsonic.models.QualityTier
import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
import nl.teunschriks.mumamobile.home.TileInfo
import nl.teunschriks.mumamobile.util.Settings.maxSongs

/**
 * One filtered track list, as the server's `getSongs` understands it.
 *
 * Every browse level in the car that ends in music -- a genre, a label, a podcast, a festival, a
 * year, a lineup, a preset -- is one of these. The old tree had a separate media id per kind
 * (`MEDIA_GENRE_SONGS` knew genre and year and nothing else), so a preset built around a label
 * silently played everything of that length. Here the whole request is one value, and the
 * media id only has to say which one.
 *
 * The cluster names are the server's own: `GENRE`, `YEAR`, `PUBLISHER` (a record label),
 * `PODCAST`, `FESTIVAL`, `ARTIST`, and `LENGTH` for the songs/sets split. `getSongs` accepts any
 * cluster type by name, which is what makes one class enough.
 *
 * Two filters are not clusters but parameters of their own: [forms] (MuMa's track/set/liveset/
 * podcast classification) and [year], the year a track *files under* -- a live set's performance
 * year where MuMa knows it, else the date tag. A year travels as [year] only together with a form,
 * which is what "Livesets 2012" asks for; everywhere else it stays the `YEAR` cluster it always was,
 * so no existing list changes meaning.
 */
data class BrowseQuery(
    /** "short" for songs, "long" for sets: the `LENGTH` cluster the tagger writes. */
    val length: String,
    val clusters: Map<String, List<String>> = emptyMap(),
    val sortMethod: String = SORT_RELEASE,
    /** A festival lineup restricts to the artists booked for it; it is not a cluster. */
    val festivalLineup: String? = null,
    val ratingMin: Int = 0,
    val ratingMax: Int = 5,
    /** Minutes, like the endpoint. Only a preset sets these. */
    val minDuration: Int? = null,
    val maxDuration: Int? = null,
    val count: Int = maxSongs,
    /** Forms from [TrackForm.FORMS]; anything else is dropped before the request. */
    val forms: List<String> = emptyList(),
    /** The filing year, sent as `year`; see the class comment for when it is used. */
    val year: Int? = null,
    /**
     * The random seed of a [SORT_RANDOM] list, sent as `seed`. Without one every page of a random
     * list is a new shuffle, so the queue's next page would repeat what already played and miss
     * the rest; with one, `offset` walks through the same shuffle (issue #103). Null for every
     * other sort, and for a random list until [seeded] picks one.
     */
    val seed: Int? = null
) {
    /** Whether the server shuffles this list, so its pages only line up under one [seed]. */
    val isRandom: Boolean get() = sortMethod.equals(SORT_RANDOM, ignoreCase = true)

    /**
     * This query with a seed of its own when it is random and has none yet, else unchanged. The
     * seed is picked once, for the first page, and travels with the query into every later page.
     */
    fun seeded(pick: () -> Int = ::randomSeed): BrowseQuery = if (isRandom && seed == null) copy(seed = pick()) else this

    fun toFilters(): Filters {
        val filters = Filters()
        clusters.forEach { (name, values) ->
            val kept = values.filter { it.isNotBlank() }
            when (kept.size) {
                0 -> Unit
                1 -> filters.add(Filter(name, kept.single()))
                else -> filters.add(Filter(name, kept))
            }
        }
        filters.add(Filter(CLUSTER_LENGTH, length))
        return filters
    }

    fun withSort(sortMethod: String): BrowseQuery = copy(sortMethod = sortMethod)

    companion object {
        const val CLUSTER_GENRE = "GENRE"
        const val CLUSTER_YEAR = "YEAR"
        const val CLUSTER_LABEL = "PUBLISHER"
        const val CLUSTER_PODCAST = "PODCAST"
        const val CLUSTER_FESTIVAL = "FESTIVAL"
        const val CLUSTER_ARTIST = "ARTIST"
        const val CLUSTER_LENGTH = "LENGTH"
        const val CLUSTER_QUALITY = QualityTier.CLUSTER

        /**
         * Not a cluster: the pseudo tag type a lineup row carries. A lineup narrows by the
         * artists booked for a festival edition, which `getSongs` takes as `festivalLineup`.
         */
        const val TAG_LINEUP = "LINEUP"

        /**
         * Not a cluster either: the pseudo tag type of a form row in the Sets tab. Its value is one
         * of [TrackForm.SET_FORMS], which `getSongs` takes as `form`.
         */
        const val TAG_FORM = "FORM"

        const val SORT_RELEASE = "DateDescAndRelease"
        const val SORT_ADDED = "AddedDesc"
        const val SORT_RANDOM = "Random"

        /** The largest seed handed out; the server multiplies it into a 32-bit expression. */
        private const val MAX_SEED = 1_000_000

        /** A fresh seed for a random list, in the web's range (`PresetView.svelte`). */
        fun randomSeed(): Int = kotlin.random.Random.nextInt(MAX_SEED)

        /**
         * A preset as the car plays it. Everything the tile knows goes in, which is the fix for
         * label, festival and artist presets that used to lose their filter on the way to the car.
         */
        fun fromTile(tile: TileInfo): BrowseQuery {
            val clusters = mutableMapOf<String, List<String>>()
            fun put(name: String, values: List<String>?) {
                val kept = values?.filter { it.isNotBlank() && it != "All" } ?: emptyList()
                if (kept.isNotEmpty()) clusters[name] = kept
            }
            put(CLUSTER_GENRE, tile.genre)
            val length = tile.length.ifBlank { "short" }
            // The web only saves a form for a sets preset; one on a songs preset would contradict
            // the LENGTH cluster and answer nothing, so it is ignored there.
            val forms = if (length == "long") listOfNotNull(TrackForm.known(tile.form)) else emptyList()
            val years = tile.year?.filter { it.isNotBlank() && it != "All" }.orEmpty()
            val filingYear = years.singleOrNull()?.toIntOrNull()?.takeIf { forms.isNotEmpty() }
            if (filingYear == null) put(CLUSTER_YEAR, years)
            put(CLUSTER_ARTIST, tile.artists)
            put(CLUSTER_LABEL, tile.label)
            put(CLUSTER_FESTIVAL, tile.festival)
            // A floor, so the list is every tier from the top down to it. A tile saved on the
            // web to test a car stereo with lossless files is exactly what this carries.
            put(CLUSTER_QUALITY, QualityTier.atLeast(tile.minQuality))

            return BrowseQuery(
                length = length,
                clusters = clusters,
                sortMethod = tile.sortMethod.ifBlank { SORT_ADDED },
                festivalLineup = tile.festivalLineup?.takeIf { it.isNotBlank() },
                ratingMin = tile.ratingMin,
                ratingMax = tile.ratingMax,
                minDuration = tile.minDuration,
                maxDuration = tile.maxDuration,
                count = tile.size.takeIf { it > 0 } ?: maxSongs,
                forms = forms,
                year = filingYear
            )
        }
    }
}

/**
 * The tag half of a media id: `<action>|<length>|<type>|<value>|<year>|<sort>`.
 *
 * `type` is a cluster name, [BrowseQuery.TAG_LINEUP], [BrowseQuery.TAG_FORM], or empty for "everything of this length"
 * (the Random row at the top of a tab). `value` is the tag as the library spells it: the car hands
 * a media id back verbatim, so the name needs no escaping as long as it holds no `|`. `year` is
 * one year or empty. The old genre chain carried the same fields in the same order, minus type.
 */
data class TagQuery(
    val length: String,
    val type: String = "",
    val value: String = "",
    val year: String = "",
    val sortMethod: String = BrowseQuery.SORT_RELEASE
) {
    fun toBrowseQuery(): BrowseQuery {
        val clusters = mutableMapOf<String, List<String>>()
        val pseudo = type == BrowseQuery.TAG_LINEUP || type == BrowseQuery.TAG_FORM
        if (type.isNotBlank() && !pseudo && value.isNotBlank()) {
            clusters[type] = listOf(value)
        }
        // A form value the app does not know narrows nothing rather than failing the request.
        val forms = if (type == BrowseQuery.TAG_FORM) listOfNotNull(TrackForm.known(value)) else emptyList()
        // Under a form the year is the filing year -- a live set's performance year -- which is
        // what "Livesets, 2012" means; elsewhere it stays the tag year.
        val filingYear = year.toIntOrNull()?.takeIf { forms.isNotEmpty() }
        if (year.isNotBlank() && filingYear == null) clusters[BrowseQuery.CLUSTER_YEAR] = listOf(year)
        return BrowseQuery(
            length = length,
            clusters = clusters,
            sortMethod = sortMethod,
            festivalLineup = value.takeIf { type == BrowseQuery.TAG_LINEUP && it.isNotBlank() },
            forms = forms,
            year = filingYear
        )
    }

    fun mediaId(action: String): String = listOf(action, length, type, value, year, sortMethod).joinToString("|")

    companion object {
        private const val INDEX_LENGTH = 1
        private const val INDEX_TYPE = 2
        private const val INDEX_VALUE = 3
        private const val INDEX_YEAR = 4
        private const val INDEX_SORT = 5

        /** Null when the id has no length: every tag query needs the songs/sets side. */
        fun parse(parts: List<String>): TagQuery? {
            val length = parts.getOrNull(INDEX_LENGTH)?.takeIf { it.isNotBlank() } ?: return null
            return TagQuery(
                length = length,
                type = parts.getOrNull(INDEX_TYPE) ?: "",
                value = parts.getOrNull(INDEX_VALUE) ?: "",
                year = parts.getOrNull(INDEX_YEAR) ?: "",
                sortMethod = parts.getOrNull(INDEX_SORT)?.takeIf { it.isNotBlank() } ?: BrowseQuery.SORT_RELEASE
            )
        }
    }
}
