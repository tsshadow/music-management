/*
 * ArtistHeaderData.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.adapters

import android.content.Context
import org.moire.ultrasonic.domain.Album
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.Identifiable

/**
 * Everything the artist page header shows, already turned into display strings.
 *
 * A data class on purpose: [BaseAdapter]'s diff callback compares items by [id] and contents by
 * equality, so the header rebinds itself when the artist metadata arrives after the album list
 * has already been submitted.
 *
 * A null field means "hide that line" rather than "show nothing there".
 */
data class ArtistHeader(
    val name: String?,
    val coverArtId: String?,
    val subtitle: String?,
    val years: String?,
    val genres: String?
) : Identifiable {
    override val id: String = HEADER_ID

    companion object {
        const val HEADER_ID = "artist_header"
    }
}

/** How many genres fit on the header's one genre line before it starts to read as a list. */
private const val MAX_GENRES = 3

/** An en dash with spaces, the typographic convention for a range of years. */
private const val YEAR_RANGE_SEPARATOR = " – "

/**
 * Builds the header from whatever is known about the artist.
 *
 * [artist] is the row from the local `artists` table and may be missing entirely - artists
 * reached through search, through paging or from a home screen card never went through the
 * cache that fills it. Everything therefore has a fallback derived from the discography that
 * the page has loaded anyway: [fallbackName] is the name the navigation arguments carried, and
 * [albums] is the album list currently on screen.
 */
fun buildArtistHeader(
    artist: Artist?,
    fallbackName: String?,
    albums: List<Album>,
    context: Context
): ArtistHeader {
    val subtitle = artistSubtitleOf(artist?.albumCount, artist?.songCount, context)
        ?: artistSubtitleOf(
            albumCount = albums.size.toLong(),
            songCount = albums.sumOf { it.songCount ?: 0L },
            context = context
        )

    return ArtistHeader(
        name = artist?.name?.takeIf { it.isNotBlank() } ?: fallbackName,
        coverArtId = artist?.coverArt,
        subtitle = subtitle,
        years = yearsActive(albums),
        genres = genresOf(artist, albums)
    )
}

/**
 * "1998 – 2020", or a single year when that is all there is. Servers report an unknown year as
 * null or as 0, and both would otherwise drag the range back to the year zero.
 */
private fun yearsActive(albums: List<Album>): String? {
    val years = albums.mapNotNull { it.year }.filter { it > 0 }
    val first = years.minOrNull() ?: return null
    val last = years.max()

    return if (first == last) first.toString() else "$first$YEAR_RANGE_SEPARATOR$last"
}

/**
 * The artist's own genre when the server reported one. Otherwise the genres of the albums on
 * screen, most common first, capped at [MAX_GENRES] so the line stays a summary.
 */
private fun genresOf(artist: Artist?, albums: List<Album>): String? {
    artist?.genre?.takeIf { it.isNotBlank() }?.let { return it }

    return albums.mapNotNull { it.genre?.takeIf { genre -> genre.isNotBlank() } }
        .groupingBy { it }
        .eachCount()
        .entries
        .sortedByDescending { it.value }
        .take(MAX_GENRES)
        .joinToString(", ") { it.key }
        .takeIf { it.isNotEmpty() }
}
