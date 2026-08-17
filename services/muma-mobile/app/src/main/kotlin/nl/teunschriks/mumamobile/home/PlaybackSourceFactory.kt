/*
 * PlaybackSourceFactory.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

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

        else -> null
    }

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
