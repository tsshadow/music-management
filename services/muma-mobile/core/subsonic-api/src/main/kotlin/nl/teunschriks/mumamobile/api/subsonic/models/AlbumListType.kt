/*
 * AlbumListOrderType.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.subsonic.models

/**
 * Type of album list used in [nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIDefinition.getAlbumList]
 * calls.
 *
 * @author Yahor Berdnikau
 */
enum class AlbumListType(val typeName: String) {
    RANDOM("random"),
    NEWEST("newest"),
    UPDATED("updated"),
    HIGHEST("highest"),
    FREQUENT("frequent"),
    RECENT("recent"),
    SORTED_BY_NAME("alphabeticalByName"),
    SORTED_BY_ARTIST("alphabeticalByArtist"),
    STARRED("starred"),
    BY_YEAR("byYear"),
    BY_GENRE("byGenre"),
    BY_TRACK_COUNT("byTrackCount")
    ;

    override fun toString(): String = typeName

    companion object {
        @JvmStatic
        fun fromName(typeName: String): AlbumListType = when (typeName) {
            in RANDOM.typeName -> RANDOM
            in NEWEST.typeName -> NEWEST
            in UPDATED.typeName -> UPDATED
            in HIGHEST.typeName -> HIGHEST
            in FREQUENT.typeName -> FREQUENT
            in RECENT.typeName -> RECENT
            in SORTED_BY_NAME.typeName -> SORTED_BY_NAME
            in SORTED_BY_ARTIST.typeName -> SORTED_BY_ARTIST
            in STARRED.typeName -> STARRED
            in BY_YEAR.typeName -> BY_YEAR
            in BY_GENRE.typeName -> BY_GENRE
            in BY_TRACK_COUNT.typeName -> BY_TRACK_COUNT
            else -> throw IllegalArgumentException("Unknown type: $typeName")
        }

        @Suppress("UnusedPrivateMember") // Used in the tests
        private operator fun String.contains(other: String) = this.equals(other, true)
    }
}
