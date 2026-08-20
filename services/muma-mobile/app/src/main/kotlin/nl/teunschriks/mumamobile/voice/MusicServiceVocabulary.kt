/*
 * MusicServiceVocabulary.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.service.MusicService
import timber.log.Timber

/**
 * The library's own names, read off a [MusicService].
 *
 * This is the only place where the voice pipeline touches the server. Everything above it -- the
 * parser, the resolver -- works against [LibraryVocabulary] and can be tested without a network.
 *
 * A failing lookup answers with an empty list rather than throwing. The resolver drops a term it
 * cannot place and runs the rest of the request, which is a far better answer to one timed-out call
 * than losing the whole utterance.
 */
class MusicServiceVocabulary(private val musicService: MusicService) : LibraryVocabulary {

    override fun genres(): List<String> = ranked.map { it.name }

    override fun prominentGenres(): List<String> {
        val biggest = ranked.firstOrNull()?.songCount ?: return emptyList()
        val floor = biggest * LibraryVocabulary.PROMINENCE_FLOOR_PERCENT / 100
        return ranked
            .filter { it.songCount >= floor }
            .take(LibraryVocabulary.PROMINENT_LIMIT)
            .map { it.name }
    }

    /**
     * Read once per instance, ordered by song count.
     *
     * A resolver is built per request and thrown away, so this is a memo for the length of one
     * request rather than a cache that can go stale. The ordering is what [LibraryVocabulary]
     * promises its callers, and it is what decides which spelling of a genre wins a tie: the
     * cluster holding twenty thousand tracks rather than whichever leftover the server listed
     * first.
     */
    private val ranked: List<Genre> by lazy {
        runCatching {
            musicService.getGenres(false, null, null).sortedByDescending { it.songCount }
        }.getOrElse {
            Timber.w(it, "voice vocabulary lookup failed: genres")
            emptyList()
        }
    }

    override fun labels(): List<String> = tagNames(TAG_PUBLISHER)

    override fun years(): List<String> = tagNames(TAG_YEAR)

    override fun ratings(): List<String> = tagNames(TAG_RATING)

    override fun artists(term: String): List<String> = safely("artists") {
        musicService
            .getArtists(false, null, ARTIST_CANDIDATES, term, null)
            .mapNotNull { it.name }
    }

    override fun albums(term: String): List<NamedRef> = safelyRefs("albums") {
        musicService
            .search(SearchCriteria(term, 0, ALBUM_CANDIDATES, 0))
            ?.albums
            .orEmpty()
            .map { NamedRef(it.id, it.title ?: it.name.orEmpty()) }
    }

    override fun playlists(): List<NamedRef> = safelyRefs("playlists") {
        musicService.getPlaylists(false).map { NamedRef(it.id, it.name) }
    }

    private fun tagNames(type: String): List<String> =
        safely(type) { musicService.getTags(false, type, null, null).map { it.name } }

    private fun safely(what: String, block: () -> List<String>): List<String> =
        runCatching(block).getOrElse {
            Timber.w(it, "voice vocabulary lookup failed: %s", what)
            emptyList()
        }

    private fun safelyRefs(what: String, block: () -> List<NamedRef>): List<NamedRef> =
        runCatching(block).getOrElse {
            Timber.w(it, "voice vocabulary lookup failed: %s", what)
            emptyList()
        }

    companion object {
        const val TAG_PUBLISHER = "PUBLISHER"
        const val TAG_YEAR = "YEAR"
        const val TAG_RATING = "RATING"

        /** How many artists the server is asked to offer for one spoken name. */
        const val ARTIST_CANDIDATES = 20

        /** How many albums the server is asked to offer for one spoken name. */
        const val ALBUM_CANDIDATES = 10
    }
}
