/*
 * FeedBrowseArea.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.text.format.DateFormat
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata.MEDIA_TYPE_PLAYLIST
import androidx.media3.common.util.UnstableApi
import java.util.Date
import kotlinx.coroutines.guava.future
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.util.toMediaItem
import org.koin.java.KoinJavaComponent.inject

/**
 * What MuMa itself serves rather than the Subsonic library: the personalized feeds (release
 * radar, the daily mixes folder and each mix) and the two live sources, radio and news.
 */
@UnstableApi
internal class FeedBrowseArea(context: BrowseContext) : BrowseArea(context) {

    // Radio talks to the MuMa backend rather than the Subsonic API, so it needs
    // the client that owns the /muma base URL and the API-key interceptor.
    private val subsonicAPIClient: SubsonicAPIClient by inject(SubsonicAPIClient::class.java)

    override fun children(
        action: String,
        parentId: String,
        parts: List<String>,
        page: Int,
        pageSize: Int
    ): BrowseResult? = when (action) {
        MEDIA_RADIO_ID -> getRadioChannelItems()
        MEDIA_NEWS_ID -> getNewsBulletinItems()
        MEDIA_FEED_ID -> {
            val slug = parts.getOrNull(INDEX_ID)
            if (slug != null) {
                getFeedItems(slug)
            } else {
                emptyResult("Missing feed slug in $parentId")
            }
        }
        MEDIA_DAILY_MIXES_ID -> getDailyMixesFolderItems()
        else -> null
    }

    /**
     * Lists the radio channels the server offers. Each one is playable rather
     * than browsable: a channel has no track list a user could pick from, only
     * whatever the server's timeline says is on air right now.
     */
    private fun getRadioChannelItems(): BrowseResult = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val channels = callWithErrorHandling {
            subsonicAPIClient.mumaApi.api.getRadioChannels().execute().body()?.channels
        } ?: emptyList()

        for (channel in channels) {
            mediaItems.add(
                title = channel.name,
                mediaId = listOf(MEDIA_RADIO_ITEM, channel.slug).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * The bulletins the server still keeps, newest first. Each one is playable
     * rather than browsable: a bulletin is a single recording, not a track list.
     */
    private fun getNewsBulletinItems(): BrowseResult = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val bulletins = callWithErrorHandling {
            subsonicAPIClient.mumaApi.api.getNewsBulletins().execute().body()?.bulletins
        } ?: emptyList()

        val formatter = DateFormat.getTimeFormat(UApp.applicationContext())
        for (bulletin in bulletins) {
            mediaItems.add(
                title = formatter.format(Date((bulletin.startedAt * 1000).toLong())),
                mediaId = listOf(MEDIA_NEWS_ITEM, bulletin.id.toString()).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * One personalized feed as a list of tracks, MuMa's order kept.
     *
     * The tracks are cached on the data provider before the items are built, because a tap in
     * the car comes back as a media id and nothing else -- the playback side has to find the
     * song again without asking who was showing it.
     *
     * The list shows at most [DISPLAY_LIMIT] tracks: the stored list can reach 500 once the web
     * has continued it, and Auto has item limits of its own. What is not listed still plays --
     * "Alles afspelen" and a tapped track queue the whole first page, and that queue continues
     * past its end on its own (ListQueueContinuation, issue #84).
     */
    private fun getFeedItems(slug: String): BrowseResult = serviceScope.future {
        val tracks = dataProvider.feeds.tracksFor(slug).take(DISPLAY_LIMIT)

        val mediaItems: MutableList<MediaItem> = ArrayList()
        if (tracks.size > 1) {
            mediaItems.addPlayAllItem(listOf(MEDIA_FEED_ID, slug).joinToString("|"))
        }
        for (track in tracks) {
            mediaItems.add(
                track.toMediaItem(
                    listOf(MEDIA_FEED_ITEM, slug, track.id).joinToString("|")
                )
            )
        }
        itemListResult(mediaItems)
    }

    /**
     * The "Daily mixes" folder: the three spectrum bands, the day's artist and the day's label,
     * then the classic, unrestricted mix last.
     *
     * Titles come from [nl.teunschriks.mumamobile.service.FeedRepository.listFeeds] -- the same
     * `describe_feed` the phone and web read -- so a car update never needs its own copy of
     * "Zachter" or "Middenin" typed into this app, and a listener without an artist/label
     * affinity yet still sees a name rather than a blank row (the server's own fallback title,
     * e.g. "Artiestmix").
     *
     * Every child is a plain `MEDIA_FEED_ID|<slug>` leaf -- the same media id [getFeedItems]
     * already answers for `release-radar` and the classic mix -- so nothing about playback
     * changes, only where the car finds them.
     */
    private fun getDailyMixesFolderItems(): BrowseResult = serviceScope.future {
        val mediaItems: MutableList<MediaItem> = ArrayList()
        val feeds = dataProvider.feeds.listFeeds().associateBy { it.slug }

        for (slug in FEED_DAILY_MIXES + FEED_DAILY_MIX + FEED_OLD_HITS) {
            mediaItems.add(
                title = feeds[slug]?.title ?: slug,
                mediaId = listOf(MEDIA_FEED_ID, slug).joinToString("|"),
                isBrowsable = false,
                mediaType = MEDIA_TYPE_PLAYLIST
            )
        }
        itemListResult(mediaItems)
    }
}
