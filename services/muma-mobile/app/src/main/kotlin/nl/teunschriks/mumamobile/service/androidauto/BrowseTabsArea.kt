/*
 * BrowseTabsArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.net.Uri
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import com.google.common.util.concurrent.Futures
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp

/**
 * The root and the four tabs under it: Start, Songs, Sets and Library.
 *
 * Every level here is static and built on the caller's thread -- no tab waits on the server
 * before it can draw. The folders the rows lead to belong to the other areas.
 */
@UnstableApi
internal class BrowseTabsArea(context: BrowseContext) : BrowseArea(context) {

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_ROOT_ID -> getRootItems()
        MEDIA_START_ID -> getStartItems()
        MEDIA_LIBRARY_ID -> getLibraryItems()
        MEDIA_SONGS_ID -> getSongsTabItems()
        MEDIA_SETS_ID -> getSetsTabItems()
        else -> null
    }

    /**
     * The four tabs. Android Auto draws the root's children as tabs and shows at most four; a
     * fifth and everything after it disappear behind a "More" tab, which is where the daily
     * mixes, the radar, radio, news and Favorites all lived while the root had nine entries.
     *
     * Start is what the car opens the app for; Songs and Sets mirror the phone's Browse grid in
     * each mode; Library is what does not depend on the mode.
     *
     * toUri rather than Uri.parse: an identical Uri.parse string anywhere in this file can
     * consume a lint baseline entry that belongs to a different row, which then fails the build
     * for code nobody touched.
     */
    private fun getRootItems(): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.auto_start, MEDIA_START_ID, imageUri = resourceArt(R.drawable.media_shuffle))
        mediaItems.add(R.string.main_songs_title, MEDIA_SONGS_ID, imageUri = resourceArt(R.drawable.ic_menu_search))
        mediaItems.add(R.string.main_sets, MEDIA_SETS_ID, imageUri = resourceArt(R.drawable.ic_menu_podcasts))
        mediaItems.add(R.string.main_library_title, MEDIA_LIBRARY_ID, imageUri = resourceArt(R.drawable.ic_menu_playlists))

        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /** An `android.resource://` uri for one of the app's own drawables. */
    private fun resourceArt(drawable: Int): Uri {
        val packageName = UApp.applicationContext().packageName
        return "android.resource://$packageName/$drawable".toUri()
    }

    /**
     * The Start tab: the personalized feeds, the favourites, and the two live sources, under
     * group headings so the car draws them as sections rather than one long list.
     *
     * Every row here is static. The presets row used to hide itself when the server listed
     * none, which cost a server round trip before the first tab could draw; it now always shows
     * and is simply empty on a fresh account. Favorite genres come from local settings and stay
     * conditional. The old `MEDIA_FAVORITES_ID` folder still answers, for a car that cached it.
     */
    private fun getStartItems(): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        mediaItems.add(R.string.main_daily_mixes_title, MEDIA_DAILY_MIXES_ID, R.string.auto_group_for_you)
        mediaItems.add(
            R.string.main_release_radar_title,
            listOf(MEDIA_FEED_ID, FEED_RELEASE_RADAR).joinToString("|"),
            R.string.auto_group_for_you
        )

        mediaItems.add(R.string.favorites_songs, MEDIA_SONG_STARRED_ID, R.string.favorites_title)
        if (context.favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_ID, R.string.favorites_title)
        }
        mediaItems.add(R.string.auto_presets, MEDIA_FAVORITE_PLAYLISTS_ID, R.string.favorites_title)

        mediaItems.add(R.string.main_radio_title, MEDIA_RADIO_ID, R.string.auto_group_live)
        mediaItems.add(R.string.main_news_title, MEDIA_NEWS_ID, R.string.auto_group_live)

        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /** The Library tab: the parts of the tree that do not depend on the mode. */
    private fun getLibraryItems(): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        mediaItems.add(R.string.playlist_label, MEDIA_PLAYLIST_ID)
        mediaItems.add(R.string.main_artists_title, MEDIA_ARTIST_ID)
        mediaItems.add(R.string.main_albums_title, MEDIA_ALBUM_ID)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /** The Songs tab: the phone's Browse grid for "short". */
    private fun getSongsTabItems(): BrowseResult = Futures.immediateFuture(itemListResult(browseTabItems("short")))

    /**
     * The Sets tab is the Songs tab for "long", plus the favourites saved for sets. Both the
     * favourite-genre and the presets row are static: a folder that is empty on open is better
     * than a tab that waits on the server before it can draw at all.
     */
    private fun getSetsTabItems(): BrowseResult {
        val mediaItems = browseTabItems("long")
        if (context.favoriteGenres().isNotEmpty()) {
            mediaItems.add(R.string.favorites_genres, MEDIA_FAVORITE_GENRES_SETS_ID, R.string.favorites_title)
        }
        mediaItems.add(R.string.auto_presets, MEDIA_FAVORITE_PLAYLISTS_SETS_ID, R.string.favorites_title)
        return Futures.immediateFuture(itemListResult(mediaItems))
    }

    /**
     * The phone's Browse grid for one mode, as two groups: the tag lists you browse through, and
     * the lists you just play. Labels and lineups only exist for songs, podcasts and festivals
     * only for sets -- the same split `collections.js` applies on the web and the phone, for the
     * same reason: the tagger writes neither tag below ten minutes, and a label describes a
     * release.
     */
    private fun browseTabItems(length: String): MutableList<MediaItem> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val browse = R.string.auto_group_browse

        mediaItems.add(R.string.main_genres_title, tagListId(length, BrowseQuery.CLUSTER_GENRE), browse)
        if (length == "long") {
            // The web sets view's Soort chip: live sets, released sets and podcasts apart, by
            // MuMa's classification rather than by the folder a file happens to sit in.
            mediaItems.add(R.string.auto_forms, tagListId(length, BrowseQuery.TAG_FORM), browse)
            mediaItems.add(R.string.auto_podcasts, tagListId(length, BrowseQuery.CLUSTER_PODCAST), browse)
            mediaItems.add(R.string.auto_festivals, tagListId(length, BrowseQuery.CLUSTER_FESTIVAL), browse)
        } else {
            mediaItems.add(R.string.library_tab_labels, tagListId(length, BrowseQuery.CLUSTER_LABEL), browse)
        }
        mediaItems.add(R.string.main_years_title, tagListId(length, BrowseQuery.CLUSTER_YEAR), browse)
        if (length == "short") {
            mediaItems.add(R.string.auto_lineups, "$MEDIA_LINEUP_LIST|$length", browse)
            // Songs only, like the web's BPM page: a set has no one tempo, and the server's BPM
            // index holds tracks only (docs/designs/android-auto-bpm/).
            mediaItems.add(R.string.auto_bpm, MEDIA_BPM_LIST, browse)
        }

        val play = R.string.auto_group_play
        mediaItems.add(
            R.string.auto_random_play,
            TagQuery(length, sortMethod = BrowseQuery.SORT_RANDOM).mediaId(MEDIA_TAG_PLAY),
            play,
            isBrowsable = false,
            mediaType = MEDIA_TYPE_PLAYLIST
        )
        mediaItems.add(R.string.main_songs_recent_added, "$MEDIA_SONG_RECENT|$length|${BrowseQuery.SORT_ADDED}", play)
        mediaItems.add(R.string.main_albums_released, "$MEDIA_SONG_RECENT|$length|${BrowseQuery.SORT_RELEASE}", play)
        return mediaItems
    }

    /** The `MEDIA_TAG_LIST|<length>|<type>` id of one tag list. */
    private fun tagListId(length: String, type: String): String = listOf(MEDIA_TAG_LIST, length, type).joinToString("|")
}
