/*
 * TagBrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import com.google.common.util.concurrent.Futures
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
import nl.teunschriks.mumamobile.coverart.BrowseArtwork
import nl.teunschriks.mumamobile.util.Settings.maxSongs
import nl.teunschriks.mumamobile.util.toMediaItem
import timber.log.Timber

/**
 * The lists behind the Songs and Sets tabs: the tag lists (genres, labels, forms, podcasts,
 * festivals, years, lineups), the one tag folder every tag row leads to with its year level, and
 * the tab's own sorted track lists. Everything here is per length -- "short" or "long".
 */
@UnstableApi
internal class TagBrowseArea(context: BrowseContext) : BrowseArea(context) {

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_SONG_RANDOM_ID -> {
            val length = parts.getOrNull(INDEX_LENGTH)
            if (length != null) {
                getSongs(length = length, sortMethod = BrowseQuery.SORT_RANDOM)
            } else {
                emptyResult("Missing length in $parentId")
            }
        }

        MEDIA_SONG_RECENT -> {
            val length = parts.getOrNull(INDEX_LENGTH)
            val sortMethod = parts.getOrNull(INDEX_NAME)
            if (length != null) {
                getSongs(length = length, sortMethod = sortMethod ?: "AddedDesc")
            } else {
                emptyResult("Missing length in $parentId")
            }
        }

        MEDIA_TAG_LIST -> {
            val query = TagQuery.parse(parts)
            if (query != null && query.type.isNotBlank()) {
                getTagList(query.length, query.type)
            } else {
                emptyResult("Missing length or type in $parentId")
            }
        }

        MEDIA_TAG_YEARS -> {
            val query = TagQuery.parse(parts)
            if (query != null) getTagYears(query) else emptyResult("Missing length in $parentId")
        }

        MEDIA_TAG_TRACKS -> {
            val query = TagQuery.parse(parts)
            if (query != null) {
                getTagFolder(query, page, pageSize)
            } else {
                emptyResult("Missing length in $parentId")
            }
        }

        MEDIA_LINEUP_LIST -> {
            val length = parts.getOrNull(INDEX_LENGTH)
            if (length != null) getLineupList(length) else emptyResult("Missing length in $parentId")
        }

        else -> null
    }

    /**
     * A Songs/Sets tab list in one order, [maxSongs] long -- the browse list stays bounded; the
     * queue a tap or "Alles afspelen" starts from it continues past that on its own (issue #103).
     */
    private fun getSongs(length: String, sortMethod: String?): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val list = serviceScope.future {
                dataProvider.loadLengthList(length, sortMethod ?: BrowseQuery.SORT_ADDED, maxSongs)
            }.await()

            if (list != null) {
                if (list.tracks.size > 1) {
                    mediaItems.addPlayAllItem(listOf(MEDIA_SONG_RANDOM_ID).joinToString("|"))
                }

                list.tracks.map { song ->
                    mediaItems.add(
                        song.toMediaItem(
                            listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|")
                        )
                    )
                }
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * The tags of one type for one length: genres, labels, podcasts, festivals or years. Every
     * row is the same tag folder, [getTagFolder], whatever the type -- which is what makes a
     * label browsable in the car with no code of its own.
     *
     * Ordered by how much there is to hear, most first, because a car list is scrolled with one
     * finger at a red light. Years are the exception and read newest first.
     */
    private fun getTagList(length: String, type: String): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        Timber.i("getTagList: type=$type length=$length")
        if (type == BrowseQuery.TAG_FORM) return Futures.immediateFuture(itemListResult(formItems(length)))
        return mainScope.future {
            val tags: List<Pair<String, Int>>? = serviceScope.future {
                callWithErrorHandling {
                    if (type == BrowseQuery.CLUSTER_GENRE) {
                        musicService.getGenres(true, null, length).map { it.name to it.songCount }
                    } else {
                        musicService.getTags(true, type, null, length).map { it.name to it.songCount }
                    }
                }
            }.await()

            val ordered = if (type == BrowseQuery.CLUSTER_YEAR) {
                tags?.sortedByDescending { it.first }
            } else {
                tags?.sortedByDescending { it.second }
            }

            ordered?.forEach { (name, _) ->
                mediaItems.add(
                    name,
                    TagQuery(length, type, name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = context.tagArt(type, name)
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * The forms a sets list can be narrowed to, one tag folder each. Static, and only the forms the
     * server knows: `getSongs` refuses an unknown `form` for the whole request, so the list is
     * [TrackForm.SET_FORMS] and nothing read from anywhere else. Empty on the songs side, where
     * every row is a track.
     */
    private fun formItems(length: String): MutableList<MediaItem> {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        if (length != "long") return mediaItems
        TrackForm.SET_FORMS.forEach { form ->
            val title = when (form) {
                TrackForm.LIVESET -> R.string.auto_form_liveset
                TrackForm.PODCAST -> R.string.auto_form_podcast
                else -> R.string.auto_form_set
            }
            mediaItems.add(
                title,
                TagQuery(length, BrowseQuery.TAG_FORM, form).mediaId(MEDIA_TAG_TRACKS),
                isBrowsable = true,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        return mediaItems
    }

    /**
     * The festival lineups. A lineup is not a tag on the files but a list of booked artists, so
     * it has its own list call; the row it leads to is still a tag folder, of the pseudo type
     * [BrowseQuery.TAG_LINEUP], which `getSongs` takes as `festivalLineup`.
     */
    private fun getLineupList(length: String): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val lineups = serviceScope.future {
                callWithErrorHandling { musicService.getLineups(true) }
            }.await()

            lineups?.sortedByDescending { it.name }?.forEach { lineup ->
                mediaItems.add(
                    lineup.name,
                    TagQuery(length, BrowseQuery.TAG_LINEUP, lineup.name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST,
                    imageUri = BrowseArtwork.forFestival(lineup.name, context.genreTints.tintFor(null))
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * The years under one tag, each leading to the same folder narrowed to that year.
     *
     * The server's year list is per length, not per tag: a year with nothing in it for this genre
     * opens an empty folder. That was already so in the old genre chain, where the year level was
     * mandatory; here it is one optional row down.
     */
    private fun getTagYears(query: TagQuery): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        return mainScope.future {
            val years = serviceScope.future {
                callWithErrorHandling {
                    musicService.getTags(true, BrowseQuery.CLUSTER_YEAR, year = null, length = query.length)
                }
            }.await()

            years?.sortedByDescending { it.name }?.forEach {
                mediaItems.add(
                    it.name,
                    query.copy(year = it.name).mediaId(MEDIA_TAG_TRACKS),
                    isBrowsable = true,
                    mediaType = MEDIA_TYPE_PLAYLIST
                )
            }
            return@future itemListResult(mediaItems)
        }
    }

    /**
     * One tag's folder: the way into the music the old chain spread over three levels.
     *
     * The old tree went genre, then a year (or "All"), then one of four sort orders, and only
     * then a list -- three taps before anything could play, and no way to see the tracks without
     * committing to an order first. Here the first page opens on the tracks themselves, newest
     * release first, with the two orders worth a row of their own as playable rows above them
     * and the year narrowing as a folder. A later page carries tracks only.
     */
    private fun getTagFolder(query: TagQuery, page: Int, pageSize: Int): BrowseResult {
        val mediaItems: MutableList<MediaItem> = ArrayList()

        if (page == 0) {
            val play = R.string.auto_group_play
            mediaItems.add(
                R.string.select_album_play_all,
                query.mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            mediaItems.add(
                R.string.auto_random_play,
                query.copy(sortMethod = BrowseQuery.SORT_RANDOM).mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            mediaItems.add(
                R.string.main_songs_recent_added,
                query.copy(sortMethod = BrowseQuery.SORT_ADDED).mediaId(MEDIA_TAG_PLAY),
                play,
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
            val hasYearLevel = query.year.isBlank() &&
                query.type != BrowseQuery.CLUSTER_YEAR &&
                query.type.isNotBlank()
            if (hasYearLevel) {
                mediaItems.add(R.string.auto_by_year, query.mediaId(MEDIA_TAG_YEARS), R.string.auto_group_browse)
            }
        }

        return mainScope.future {
            val tracks = serviceScope.future {
                dataProvider.tracksFor(query.toBrowseQuery(), page, pageSize)
            }.await()

            tracks?.forEach { song ->
                mediaItems.add(
                    song.toMediaItem(listOf(MEDIA_SONG_RANDOM_ITEM, song.id).joinToString("|"))
                )
            }
            return@future itemListResult(mediaItems)
        }
    }
}
