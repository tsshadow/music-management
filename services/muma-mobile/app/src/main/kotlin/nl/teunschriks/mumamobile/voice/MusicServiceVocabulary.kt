/*
 * MusicServiceVocabulary.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import nl.teunschriks.mumamobile.api.muma.MumaPodcastRule
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.service.MusicService
import org.koin.java.KoinJavaComponent
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
 *
 * @param approvedPodcasts the curated podcast shows with their aliases, from MuMa's
 *        `/api/rules/podcasts?state=white`. Only used to widen what a spoken show name can match;
 *        the names sent are always the server's own `PODCAST` values. A parameter so a test can
 *        hand in a list instead of a network client.
 */
class MusicServiceVocabulary(
    private val musicService: MusicService,
    private val approvedPodcasts: () -> List<MumaPodcastRule> = { fetchApprovedPodcasts() }
) : LibraryVocabulary {

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

    override fun festivals(): List<String> = tagNames(TAG_FESTIVAL)

    /**
     * The `PODCAST` tag values, most episodes first, each with the aliases MuMa's curation holds
     * for the show of that name.
     *
     * The tag list decides which shows exist: a curated show with no tagged episode is not
     * offered, because the server would refuse its name as a filter value. The curation list only
     * lends aliases, matched to a tag value by name ignoring case and punctuation; when it cannot
     * be reached the shows are still matched by their own names.
     */
    override fun podcasts(): List<PodcastShow> {
        val tags = runCatching { musicService.getTags(false, TAG_PODCAST, null, null) }.getOrElse {
            Timber.w(it, "voice vocabulary lookup failed: %s", TAG_PODCAST)
            return emptyList()
        }
        if (tags.isEmpty()) return emptyList()

        val aliases = runCatching { approvedPodcasts() }.getOrElse {
            Timber.w(it, "voice vocabulary lookup failed: podcast aliases")
            emptyList()
        }.groupBy({ keyOf(it.name) }, { it.aliases })

        return tags
            .sortedWith(compareByDescending<Tag> { it.songCount }.thenBy { it.name.lowercase() })
            .map { tag ->
                val known = aliases[keyOf(tag.name)].orEmpty().flatten()
                PodcastShow(tag.name, known.filterNot { keyOf(it) == keyOf(tag.name) }.distinct())
            }
    }

    private fun tagNames(type: String): List<String> = safely(type) { musicService.getTags(false, type, null, null).map { it.name } }

    private fun safely(what: String, block: () -> List<String>): List<String> = runCatching(block).getOrElse {
        Timber.w(it, "voice vocabulary lookup failed: %s", what)
        emptyList()
    }

    private fun safelyRefs(what: String, block: () -> List<NamedRef>): List<NamedRef> = runCatching(block).getOrElse {
        Timber.w(it, "voice vocabulary lookup failed: %s", what)
        emptyList()
    }

    companion object {
        const val TAG_PUBLISHER = "PUBLISHER"
        const val TAG_YEAR = "YEAR"
        const val TAG_RATING = "RATING"
        const val TAG_FESTIVAL = "FESTIVAL"
        const val TAG_PODCAST = "PODCAST"

        /** Enough for every curated show; the queue endpoint caps at whatever it is asked for. */
        const val PODCAST_RULES_LIMIT = 1000

        /** The same loose comparison the resolver's matching uses: letters and digits only. */
        private fun keyOf(name: String): String = name.lowercase().filter { it.isLetterOrDigit() }

        /** The approved shows from MuMa, through the one API client the app shares. */
        private fun fetchApprovedPodcasts(): List<MumaPodcastRule> = KoinJavaComponent.get<SubsonicAPIClient>(SubsonicAPIClient::class.java)
            .mumaApi.api.getPodcastRules("white", PODCAST_RULES_LIMIT).execute().body().orEmpty()

        /** How many artists the server is asked to offer for one spoken name. */
        const val ARTIST_CANDIDATES = 20

        /** How many albums the server is asked to offer for one spoken name. */
        const val ALBUM_CANDIDATES = 10
    }
}
