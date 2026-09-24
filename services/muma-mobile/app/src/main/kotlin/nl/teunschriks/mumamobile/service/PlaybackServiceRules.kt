/*
 * PlaybackServiceRules.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

/**
 * The decisions [PlaybackService] makes that need no Android object to answer, kept apart so a
 * JVM test can pin them: what the data-source resolver does with an item's URI, and whether a
 * swipe-away stops the service.
 */
object PlaybackServiceRules {

    /** What the resolver has to do with the URI an item reached the player with. */
    sealed class StreamTarget {
        /** A finished http(s) stream URL -- radio builds its own -- that goes out unchanged. */
        object Direct : StreamTarget()

        /** A library track, carried as `id|bitrate|path`, whose stream URL is built on demand. */
        data class Track(val id: String, val bitrate: Int) : StreamTarget()
    }

    /**
     * Classifies an item URI that missed the local cache.
     *
     * Every local-player item passes through the resolver, including radio's, whose URI is
     * already the authenticated, transcoded stream URL. Only the `id|bitrate|path` shape of a
     * library track needs a stream URL built for it. A bitrate that is missing or not a number
     * falls back to 0, the server's own default, rather than failing the load.
     */
    fun streamTargetOf(uri: String): StreamTarget {
        if (isHttpUrl(uri)) return StreamTarget.Direct
        val components = uri.split('|')
        return StreamTarget.Track(
            id = components[0],
            bitrate = components.getOrNull(1)?.toIntOrNull() ?: 0
        )
    }

    private fun isHttpUrl(uri: String): Boolean = uri.startsWith("http://", ignoreCase = true) ||
        uri.startsWith("https://", ignoreCase = true)

    /**
     * Whether swiping the app away should stop the service: only when nothing is playing or
     * about to play. A queue that is playing, or buffering towards playing, keeps going.
     */
    fun shouldStopOnTaskRemoved(playWhenReady: Boolean, mediaItemCount: Int): Boolean = !playWhenReady || mediaItemCount == 0
}
