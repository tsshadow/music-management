/*
 * MediaItemConverter.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Bundle
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_FOLDER_MIXED
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_MUSIC
import androidx.media3.common.StarRating
import com.google.gson.Gson
import java.text.DateFormat
import java.text.ParseException
import java.util.Date
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.provider.AlbumArtContentProvider

// Copied from androidx.media.utils.MediaConstants in order to avoid importing a whole dependency
// for a single string value
private const val DESCRIPTION_EXTRAS_KEY_CONTENT_STYLE_GROUP_TITLE =
    "android.media.browse.CONTENT_STYLE_GROUP_TITLE_HINT"

// Ratings run from 0 to 5 everywhere; 5 is the highest and means favorite.
const val MAX_STARS = 5

object MediaItemConverter {
    private const val CACHE_SIZE = 250
    private const val CACHE_EXPIRY_MINUTES = 10L

    val mediaItemCache: LRUCache<String, TimeLimitedCache<MediaItem>> = LRUCache(CACHE_SIZE)
    val trackCache: LRUCache<String, TimeLimitedCache<Track>> = LRUCache(CACHE_SIZE)

    /**
     * Adds a MediaItem to the cache with default expiry time
     */
    fun addToCache(key: String, item: MediaItem) {
        val cache: TimeLimitedCache<MediaItem> = TimeLimitedCache(CACHE_EXPIRY_MINUTES)
        cache.set(item)
        mediaItemCache.put(key, cache)
    }

    /**
     * Add a Track object to the cache with default expiry time
     */
    fun addToCache(key: String, item: Track) {
        val cache: TimeLimitedCache<Track> = TimeLimitedCache(CACHE_EXPIRY_MINUTES)
        cache.set(item)
        trackCache.put(key, cache)
    }

    /**
     * Records a rating that was set somewhere other than on the playing item.
     *
     * The cached Track can be corrected in place, but the cached MediaItem cannot: its metadata
     * has the rating as an immutable StarRating, so it is dropped instead and the next
     * [toMediaItem] builds a fresh one from the up-to-date Track.
     *
     * [trackId] is a track id, and every entry for that track is corrected: the plain one and the
     * composite ids the car's browse tree builds (`<list>|<track id>`, `bpm|<bucket>|<track id>`).
     * Before issue #256 only the entry with exactly that key was, so a list in the car kept the old
     * rating for ten minutes.
     */
    fun applyRating(trackId: String, rating: Int) {
        for (key in trackCache.keys()) {
            val track = trackCache[key]?.get()
            if (isEntryFor(key, trackId) || track?.id == trackId) track?.userRating = rating
        }
        for (key in mediaItemCache.keys()) {
            if (isEntryFor(key, trackId)) mediaItemCache.remove(key)
        }
    }

    /**
     * The rating the caches know for [mediaId], or null when they know none. Read by [toMediaItem]
     * so that a Track built without a rating does not replace one that has it.
     */
    fun cachedRating(mediaId: String): Int? = trackCache[mediaId]?.get()?.userRating
        ?: mediaItemCache[mediaId]?.get()?.ratingExtra()

    /** Whether the cache key [key] is an entry for the track [trackId]. */
    fun isEntryFor(key: String, trackId: String): Boolean = key == trackId || key.substringAfterLast('|') == trackId
}

/** The rating stored in the item's extras, or null when it has none: unknown. */
fun MediaItem.ratingExtra(): Int? {
    val extras = mediaMetadata.extras ?: return null
    return if (extras.containsKey("userRating")) extras.getInt("userRating") else null
}

/**
 * Extension function to convert a Track to an MediaItem, using the cache if possible
 */
@Suppress("LongMethod")
fun Track.toMediaItem(mediaId: String = id): MediaItem {
    // Check Cache. A Track without a rating takes the cached item, which may know it. A Track with
    // one only takes an item built with the same rating: the newer value wins (issue #256).
    val cachedItem = MediaItemConverter.mediaItemCache[mediaId]?.get()
    if (cachedItem != null && (userRating == null || cachedItem.ratingExtra() == userRating)) return cachedItem
    if (userRating == null) userRating = MediaItemConverter.cachedRating(mediaId)

    // No cache hit, generate it
    val filePath = FileUtil.getSongFile(this)
    val bitrate = Settings.maxBitRate
    val uri = "$id|$bitrate|$filePath"

    val artworkUri = AlbumArtContentProvider.mapArtworkToContentProviderUri(this)

    val mediaItem = buildMediaItem(
        title = title ?: "",
        mediaId = mediaId,
        isPlayable = !isDirectory,
        isBrowsable = isDirectory,
        album = album,
        artist = artist,
        genre = genre,
        sourceUri = uri.toUri(),
        imageUri = artworkUri,
        userRating = userRating,
        group = null,
        mediaType = if (isDirectory) {
            MEDIA_TYPE_FOLDER_MIXED
        } else {
            MEDIA_TYPE_MUSIC
        }
    )

    val metadataBuilder = mediaItem.mediaMetadata.buildUpon()
        .setTrackNumber(track)
        .setReleaseYear(year)
        .setTotalTrackCount(songCount?.toInt())
        .setDiscNumber(discNumber)

    mediaItem.mediaMetadata.extras?.putInt("serverId", serverId)
    mediaItem.mediaMetadata.extras?.putString("parent", parent)
    mediaItem.mediaMetadata.extras?.putString("albumId", albumId)
    mediaItem.mediaMetadata.extras?.putString("artistId", artistId)
    mediaItem.mediaMetadata.extras?.putString("contentType", contentType)
    mediaItem.mediaMetadata.extras?.putString("suffix", suffix)
    mediaItem.mediaMetadata.extras?.putString("transcodedContentType", transcodedContentType)
    mediaItem.mediaMetadata.extras?.putString("transcodedSuffix", transcodedSuffix)
    mediaItem.mediaMetadata.extras?.putString("coverArt", coverArt)
    if (size != null) mediaItem.mediaMetadata.extras?.putLong("size", size!!)
    if (duration != null) mediaItem.mediaMetadata.extras?.putInt("duration", duration!!)
    if (bitRate != null) mediaItem.mediaMetadata.extras?.putInt("bitRate", bitRate!!)
    mediaItem.mediaMetadata.extras?.putString("path", path)
    mediaItem.mediaMetadata.extras?.putBoolean("isVideo", isVideo)
    mediaItem.mediaMetadata.extras?.putBoolean("starred", starred)
    mediaItem.mediaMetadata.extras?.putString("type", type)
    if (created != null) {
        mediaItem.mediaMetadata.extras?.putString(
            "created",
            DateFormat.getDateInstance().format(created!!)
        )
    }
    mediaItem.mediaMetadata.extras?.putInt("closeness", closeness)
    mediaItem.mediaMetadata.extras?.putInt("bookmarkPosition", bookmarkPosition)
    mediaItem.mediaMetadata.extras?.putString("name", name)
    if (!genres.isNullOrEmpty()) {
        mediaItem.mediaMetadata.extras?.putString(
            "genreValues",
            Gson().toJson(genres)
        )
    }
    if (userRating != null) {
        mediaItem.mediaMetadata.extras?.putInt("userRating", userRating!!)
        metadataBuilder.setUserRating(StarRating(MAX_STARS, userRating!!.coerceIn(0, MAX_STARS).toFloat()))
    }
    if (averageRating != null) {
        mediaItem.mediaMetadata.extras?.putFloat("averageRating", averageRating!!)
        metadataBuilder.setOverallRating(StarRating(5, averageRating!!))
    }

    val item = mediaItem.buildUpon().setMediaMetadata(metadataBuilder.build()).build()

    // Add MediaItem and Track to the cache
    MediaItemConverter.addToCache(mediaId, item)
    MediaItemConverter.addToCache(mediaId, this)

    return item
}

/**
 * Extension function to convert a MediaItem to a Track, using the cache if possible
 */
@Suppress("ComplexMethod")
fun MediaItem.toTrack(): Track {
    // Check Cache
    val cachedTrack = MediaItemConverter.trackCache[mediaId]?.get()
    if (cachedTrack != null) return cachedTrack

    // No cache hit, generate it
    val created = mediaMetadata.extras?.getString("created")
    val createdDate = safeParseDate(created)
    // Array<String>::class.java rather than an anonymous TypeToken: R8 full mode strips the
    // generic superclass of those, making TypeToken.getType() throw in release builds.
    val genres: List<String>? = mediaMetadata.extras?.getString("genreValues")?.let {
        Gson().fromJson(it, Array<String>::class.java)?.toList()
    }
    val track = Track(
        mediaId,
        mediaMetadata.extras?.getInt("serverId") ?: -1,
        mediaMetadata.extras?.getString("parent"),
        !(mediaMetadata.isPlayable ?: true),
        mediaMetadata.title as String?,
        mediaMetadata.albumTitle as String?,
        mediaMetadata.extras?.getString("albumId"),
        mediaMetadata.artist as String?,
        mediaMetadata.extras?.getString("artistId"),
        mediaMetadata.trackNumber,
        mediaMetadata.releaseYear,
        mediaMetadata.genre as String?,
        genres,
        mediaMetadata.extras?.getString("date"),
        mediaMetadata.extras?.getString("contentType"),
        mediaMetadata.extras?.getString("suffix"),
        mediaMetadata.extras?.getString("transcodedContentType"),
        mediaMetadata.extras?.getString("transcodedSuffix"),
        mediaMetadata.extras?.getString("coverArt"),
        if (mediaMetadata.extras?.containsKey("size") == true) {
            mediaMetadata.extras?.getLong("size")
        } else {
            null
        },
        mediaMetadata.totalTrackCount?.toLong(),
        if (mediaMetadata.extras?.containsKey("duration") == true) {
            mediaMetadata.extras?.getInt("duration")
        } else {
            null
        },
        if (mediaMetadata.extras?.containsKey("bitRate") == true) {
            mediaMetadata.extras?.getInt("bitRate")
        } else {
            null
        },
        mediaMetadata.extras?.getString("path"),
        mediaMetadata.extras?.getBoolean("isVideo") ?: false,
        mediaMetadata.extras?.getBoolean("starred", false) ?: false,
        mediaMetadata.discNumber,
        mediaMetadata.extras?.getString("type"),
        createdDate,
        mediaMetadata.extras?.getInt("closeness", 0) ?: 0,
        mediaMetadata.extras?.getInt("bookmarkPosition", 0) ?: 0,
        ratingExtra(),
        mediaMetadata.extras?.getFloat("averageRating", 0F) ?: 0F,
        mediaMetadata.extras?.getString("name")
    )
    // Only a fallback, for items built without an extras entry of their own. The metadata's
    // StarRating is frozen when the item is built - MediaMetadata is immutable, so
    // [setUserRating] can never reach it - while the extras stay current. Letting it win would
    // hand a rating changed in the car back the number the item was built with, and the next tap
    // would recompute the rating that was just set.
    // An unrated StarRating is "unknown", not 0: the car's rating button would step from it and
    // write 1 over a real rating (issue #256).
    if (mediaMetadata.extras?.containsKey("userRating") != true) {
        (mediaMetadata.userRating as? StarRating)?.takeIf { it.isRated }?.let {
            track.userRating = it.starRating.toInt()
        }
    }

    // Add MediaItem and Track to the cache
    MediaItemConverter.addToCache(mediaId, track)
    MediaItemConverter.addToCache(mediaId, this)

    return track
}

/**
 * Records a rating on the item, in both places a later read can come from.
 *
 * [toTrack] answers from the track cache while it holds the entry, and rebuilds from the item's
 * metadata once the entry has expired - ten minutes, which a paused or long track outlives. Writing
 * only the cached Track would therefore let the rating the item was built with come back and send
 * the next rating change off the wrong number.
 */
fun MediaItem.setUserRating(rating: Int) {
    toTrack().userRating = rating
    mediaMetadata.extras?.putInt("userRating", rating)
}

private fun safeParseDate(created: String?): Date? = if (created != null) {
    try {
        DateFormat.getDateInstance().parse(created)
    } catch (_: ParseException) {
        null
    }
} else {
    null
}

/**
 * Build a new MediaItem from a list of attributes.
 * Especially useful to create folder entries in the Auto interface.
 *
 * [userRating] null means the rating is not known, which is not the same as 0 (issue #256).
 */
@SuppressLint("UnsafeOptInUsageError")
@Suppress("LongParameterList")
fun buildMediaItem(
    title: String,
    mediaId: String,
    isPlayable: Boolean,
    isBrowsable: Boolean = false,
    album: String? = null,
    artist: String? = null,
    genre: String? = null,
    sourceUri: Uri? = null,
    imageUri: Uri? = null,
    userRating: Int? = null,
    group: String? = null,
    mediaType: @MediaMetadata.MediaType Int? = null
): MediaItem {
    val metadataBuilder = MediaMetadata.Builder()
        .setAlbumTitle(album)
        .setTitle(title)
        .setSubtitle(artist) // Android Auto only displays this field with Title
        .setArtist(artist)
        .setAlbumArtist(artist)
        .setGenre(genre)
        .setUserRating(
            if (userRating != null && userRating > 0) {
                StarRating(MAX_STARS, userRating.coerceAtMost(MAX_STARS).toFloat())
            } else {
                StarRating(MAX_STARS)
            }
        )
        .setIsBrowsable(isBrowsable)
        .setIsPlayable(isPlayable)

    if (imageUri != null) {
        metadataBuilder.setArtworkUri(imageUri)
    }

    if (mediaType != null) {
        metadataBuilder.setMediaType(mediaType)
    }

    if (group != null) {
        metadataBuilder.setExtras(
            Bundle().apply {
                putString(
                    DESCRIPTION_EXTRAS_KEY_CONTENT_STYLE_GROUP_TITLE,
                    group
                )
            }
        )
    } else {
        metadataBuilder.setExtras(Bundle())
    }

    val metadata = metadataBuilder.build()
    // The extras are what [toTrack] reads the rating from. Null leaves them without one: unknown.
    if (userRating != null) metadata.extras?.putInt("userRating", userRating)

    val mediaItemBuilder = MediaItem.Builder()
        .setMediaId(mediaId)
        .setMediaMetadata(metadata)
        .setUri(sourceUri)

    if (sourceUri != null) {
        mediaItemBuilder.setRequestMetadata(
            MediaItem.RequestMetadata.Builder()
                .setMediaUri(sourceUri)
                .build()
        )
    }

    return mediaItemBuilder.build()
}
