/*
 * PlaybackSourceFactory.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import com.google.gson.Gson
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.fragment.TrackCollectionFragmentArgs

/**
 * What a track collection screen means as a place to go back to.
 *
 * This is the inverse of [HomeCardNavigator]: that turns a card into a screen, this turns the
 * arguments a screen was opened with back into the card. Pairing them is what makes a shortcut
 * round-trip -- play out of Raw Hardstyle, and tapping the shortcut later re-runs the genre query
 * rather than replaying the tracks that happened to be there at the time. Different songs, same
 * corner of the library.
 *
 * Not every screen is a destination. Shuffle-all, a starred list and a shared link produce nothing:
 * there is no query to re-run, so a shortcut to them would be a shortcut to a moment rather than to
 * a place.
 *
 * A note on fidelity: the card carries the identifying *tag* (genre, festival, lineup, album,
 * artist, playlist), not the full set of filters the screen was showing. Replaying a genre shortcut
 * therefore re-queries that genre under the standard home sort, not under whatever sort and rating
 * range were on screen at the time. Carrying those too would mean writing a
 * [nl.teunschriks.mumamobile.fragment.muma.TileInfo] payload, which is the DYNAMIC_PLAYLIST
 * path -- worth doing if the loss is ever felt, but it is a bigger change than it looks and it
 * cannot be unit tested, because that file initialises colours at class load.
 */
object PlaybackSourceFactory {

    /**
     * Ordered most specific first: a screen opened as a playlist *of* an album is a playlist, and a
     * lineup filtered *by* genre is still the lineup the user went to.
     */
    fun forTrackCollection(args: TrackCollectionFragmentArgs): HomeCard? = when {
        // A one-off: no query behind it, so nothing worth a shortcut.
        args.getRandom || args.getStarred || args.shareId != null -> null

        args.playlistId.isUsable() -> card(
            HomeCardType.STATIC_PLAYLIST,
            args.playlistId!!,
            args.playlistName ?: args.name,
            coverArtId = args.playlistId
        )

        args.isAlbum && args.id.isUsable() ->
            card(HomeCardType.ALBUM, args.id!!, args.name, coverArtId = args.id)

        args.isArtist && args.id.isUsable() -> card(HomeCardType.ARTIST, args.id!!, args.name)

        args.festivalLineup.isUsable() ->
            card(HomeCardType.LINEUP, args.festivalLineup!!, args.songs ?: args.name)

        args.festival.isUsable() ->
            card(HomeCardType.FESTIVAL, args.festival!!, args.songs ?: args.name)

        args.genre.isUsable() -> card(HomeCardType.GENRE, args.genre!!, args.songs ?: args.name)

        args.label.isUsable() -> card(HomeCardType.LABEL, args.label!!, args.songs ?: args.name)

        args.year.isUsable() -> card(HomeCardType.YEAR, args.year!!, args.songs ?: args.name)

        else -> taggedCard(args)
    }

    /**
     * The tag a filtered screen was opened with.
     *
     * Nothing in the app fills the `genre`, `label`, `festival` or `year` arguments above -- every
     * browse screen ships its tag inside the `filters` JSON instead (see [HomeCardNavigator] and
     * `TileInfo`). Reading only the arguments therefore recognised a playlist, an album, an artist
     * and a lineup, and nothing else: play out of Raw Hardstyle and the queue looked source-less.
     * The arguments are still honoured above, because they are part of the destination's contract
     * and a caller may start using them.
     *
     * `LENGTH` is the mode toggle rather than a place, and `ARTIST` filters by name where an artist
     * card needs an id, so neither yields a shortcut.
     */
    private fun taggedCard(args: TrackCollectionFragmentArgs): HomeCard? {
        val filters = parseFilters(args.filters) ?: return null

        // Most specific first: a festival lineup filtered by genre is still the festival.
        for ((filter, type) in TAG_CARD_TYPES) {
            val value = filters.singleValueOf(filter) ?: continue

            return card(type, value, args.songs?.takeIf { it.isNotBlank() } ?: value)
        }

        return null
    }

    private fun parseFilters(json: String?): Filters? = try {
        json?.takeIf { it.isNotBlank() }?.let { Gson().fromJson(it, Filters::class.java) }
    } catch (_: Exception) {
        // A screen opened with an unreadable filter set is not worth a shortcut, and must not
        // take the playback that is starting down with it.
        null
    }

    /**
     * One tag means one place. A filter holding several values (the multi-select browse screen can
     * send `GENRE: [Raw, Uptempo]`) is a combination the grid has no card for, so it is skipped
     * rather than reduced to whichever value happens to come first.
     */
    private fun Filters.singleValueOf(name: String): String? {
        val value = getAll().singleOrNull { it.name == name }?.value ?: return null

        return when (value) {
            is String -> value.takeIf { it.isNotBlank() }
            is Collection<*> -> value.singleOrNull()?.toString()?.takeIf { it.isNotBlank() }
            else -> null
        }
    }

    private val TAG_CARD_TYPES = listOf(
        "FESTIVAL" to HomeCardType.FESTIVAL,
        "PODCAST" to HomeCardType.PODCAST,
        "GENRE" to HomeCardType.GENRE,
        "PUBLISHER" to HomeCardType.LABEL,
        "YEAR" to HomeCardType.YEAR
    )

    /**
     * The title falls back to the id, which for a tag card *is* the human-readable name.
     *
     * An album and a playlist are keyed by their own id everywhere else in the app
     * ([nl.teunschriks.mumamobile.home.toHomeCard]), so the same id makes the shortcut show its
     * cover instead of a placeholder. A tag has no artwork of its own; [ShortcutsProvider] borrows
     * one from the library for those.
     */
    private fun card(
        type: HomeCardType,
        itemId: String,
        title: String?,
        coverArtId: String? = null
    ): HomeCard = HomeCard(
        type = type,
        itemId = itemId,
        title = title?.takeIf { it.isNotBlank() } ?: itemId,
        coverArtId = coverArtId
    )

    private fun String?.isUsable(): Boolean = !this.isNullOrBlank()
}
