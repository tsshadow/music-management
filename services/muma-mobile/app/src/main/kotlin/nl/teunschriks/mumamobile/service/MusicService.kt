/*
 * MusicService.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.service

import java.io.InputStream
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.domain.Album
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.Bookmark
import nl.teunschriks.mumamobile.domain.ChatMessage
import nl.teunschriks.mumamobile.domain.Genre
import nl.teunschriks.mumamobile.domain.Index
import nl.teunschriks.mumamobile.domain.JukeboxStatus
import nl.teunschriks.mumamobile.domain.Label
import nl.teunschriks.mumamobile.domain.Lineup
import nl.teunschriks.mumamobile.domain.Lyrics
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Mood
import nl.teunschriks.mumamobile.domain.MumaTile
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.MusicFolder
import nl.teunschriks.mumamobile.domain.Playlist
import nl.teunschriks.mumamobile.domain.PodcastsChannel
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.SearchResult
import nl.teunschriks.mumamobile.domain.Share
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.domain.UserInfo
import nl.teunschriks.mumamobile.domain.Year

@Suppress("TooManyFunctions")
interface MusicService {
    @Throws(Exception::class)
    fun ping()

    @Throws(Exception::class)
    fun isLicenseValid(): Boolean

    @Throws(Exception::class)
    fun getGenres(refresh: Boolean, year: Int? = null, length: String? = null): List<Genre>

    @Throws(Exception::class)
    fun getTags(refresh: Boolean, name: String, year: Int?, length: String?): List<Tag>

    /**
     * Release anniversaries for [date] (yyyy-MM-dd), newest year first.
     *
     * The caller passes the device's own date, so that a phone in another time zone gets its own
     * "today" rather than the server's.
     */
    @Throws(Exception::class)
    fun getMemories(date: String): List<MemoryGroup>

    @Throws(Exception::class)
    fun getLineups(refresh: Boolean): List<Lineup>

    @Throws(Exception::class)
    fun getMoods(refresh: Boolean, year: Int?, length: String?): List<Mood>

    @Throws(Exception::class)
    fun getYears(refresh: Boolean): List<Year>

    @Throws(Exception::class)
    fun star(id: String?, albumId: String? = null, artistId: String? = null)

    @Throws(Exception::class)
    fun unstar(id: String?, albumId: String? = null, artistId: String? = null)

    @Throws(Exception::class)
    fun setRating(id: String, rating: Int)

    @Throws(Exception::class)
    fun getMusicFolders(refresh: Boolean): List<MusicFolder>

    @Throws(Exception::class)
    fun getIndexes(musicFolderId: String?, refresh: Boolean): List<Index>

    @Throws(Exception::class)
    fun getArtists(
        refresh: Boolean,
        offset: Int? = null,
        count: Int? = null,
        query: String? = null,
        sortBy: String? = null
    ): List<Artist>

    /**
     * Artists ordered by library activity. [type] is "newest" (recently added) or
     * "updated" (recently rewritten metadata).
     */
    @Throws(Exception::class)
    fun getArtistList(type: String, size: Int): List<Artist>

    /**
     * Record labels ordered by library activity, using the same [type] values as [getArtistList].
     */
    @Throws(Exception::class)
    fun getLabelList(type: String, size: Int): List<Label>

    /**
     * A single artist by id, for the fields a list did not carry -- notably [Artist.coverArt].
     * Null when the server does not know the id.
     */
    @Throws(Exception::class)
    fun getArtist(id: String): Artist?

    @Throws(Exception::class)
    fun getArtistInfo(id: String): Artist?

    @Throws(Exception::class)
    fun getMusicDirectory(id: String, name: String?, refresh: Boolean): MusicDirectory

    @Throws(Exception::class)
    fun getAlbumsOfArtist(id: String, name: String?, refresh: Boolean): List<Album>

    @Throws(Exception::class)
    fun getAlbumAsDir(id: String, name: String?, refresh: Boolean): MusicDirectory

    @Throws(Exception::class)
    fun getAlbum(id: String, name: String?, refresh: Boolean): Album?

    @Throws(Exception::class)
    fun getSingles(artistId: String, refresh: Boolean): MusicDirectory

    @Throws(Exception::class)
    fun search(criteria: SearchCriteria): SearchResult?

    @Throws(Exception::class)
    fun getPlaylist(id: String, name: String): MusicDirectory

    @Throws(Exception::class)
    fun getPodcastsChannels(refresh: Boolean): List<PodcastsChannel>

    @Throws(Exception::class)
    fun getPlaylists(refresh: Boolean): List<Playlist>

    @Throws(Exception::class)
    fun createPlaylist(id: String?, name: String?, tracks: List<Track>)

    @Throws(Exception::class)
    fun deletePlaylist(id: String)

    @Throws(Exception::class)
    fun updatePlaylist(id: String, name: String?, comment: String?, pub: Boolean)

    @Throws(Exception::class)
    fun getLyrics(artist: String, title: String): Lyrics?

    /**
     * @param playedSeconds How long the track was actually played, or null when it is not known.
     * @param source Where the play happened: `mobile`, or `auto` when the phone is in the car.
     */
    @Throws(Exception::class)
    fun scrobble(id: String, submission: Boolean, playedSeconds: Long? = null, source: String? = null)

    @Throws(Exception::class)
    fun getAlbumList(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?
    ): List<Album>

    @Throws(Exception::class)
    fun getAlbumList2(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?,
        query: String? = null
    ): List<Album>

    @Throws(Exception::class)
    fun getRandomSongs(size: Int): MusicDirectory

    /**
     * The songs behind a list of library-relative paths, in the order they were asked for.
     *
     * What turns a personalized feed into something playable: music-manager ranks the tracks
     * and knows them by path, the streaming server knows them by id. A path the server does
     * not have is missing from the result rather than null in it, so the answer can be shorter
     * than the request.
     */
    @Throws(Exception::class)
    fun getSongsByPath(paths: List<String>): MusicDirectory

    @Throws(Exception::class)
    fun getSongsByGenre(
        genre: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory

    // One filtered track query with a lot of optional dimensions. Bundling them into a parameter
    // object would only move the same list one call deeper, and every caller passes defaults.
    @Suppress("LongParameterList")
    @Throws(Exception::class)
    fun getSongs(
        filters: Filters,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int,
        sortMethod: String?,
        festivalLineup: String? = null,
        minDuration: Int? = null,
        maxDuration: Int? = null,
        /** Artist entity ids; a track has to involve every one of them to match. */
        artistIds: List<String>? = null,
        /** One song's work id: returns every version of it, best first. */
        workId: Int? = null,
        /**
         * One row per song. Null follows the user's setting, which is what every browsing
         * caller wants; pass false where every file has to be listed.
         */
        canonicalOnly: Boolean? = null
    ): MusicDirectory

    @Throws(Exception::class)
    fun getSongsByMood(
        mood: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory

    @Throws(Exception::class)
    fun getSongsByYear(
        year: Int,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory

    @Throws(Exception::class)
    fun getStarred(): SearchResult

    @Throws(Exception::class)
    fun getStarred2(): SearchResult

    /**
     * Return response [InputStream] and a [Boolean] that indicates if this response is
     * partial.
     */
    @Throws(Exception::class)
    fun getDownloadInputStream(
        song: Track,
        offset: Long,
        maxBitrate: Int,
        save: Boolean
    ): Pair<InputStream, Boolean>

    @Throws(Exception::class)
    fun getStreamUrl(id: String, maxBitRate: Int?, format: String?): String?

    /**
     * Stream URL that actually carries maxBitRate/format/timeOffset as query
     * parameters, unlike [getStreamUrl], which drops them.
     *
     * Radio needs all three: LMS only honours `timeOffset` on its transcoding
     * path (MediaRetrieval.cpp:146-147), so joining a channel mid-track without
     * an explicit format silently starts the track from the beginning.
     */
    fun getTranscodedStreamUrl(
        id: String,
        maxBitRate: Int?,
        format: String?,
        timeOffset: Int?
    ): String?

    fun isJukeboxAvailable(): Boolean

    @Throws(Exception::class)
    fun updateJukeboxPlaylist(ids: List<String>): JukeboxStatus

    @Throws(Exception::class)
    fun skipJukebox(index: Int, offsetSeconds: Int): JukeboxStatus

    @Throws(Exception::class)
    fun stopJukebox(): JukeboxStatus

    @Throws(Exception::class)
    fun clearJukebox(): JukeboxStatus

    @Throws(Exception::class)
    fun startJukebox(): JukeboxStatus

    @Throws(Exception::class)
    fun getJukeboxStatus(): JukeboxStatus

    @Throws(Exception::class)
    fun setJukeboxGain(gain: Float): JukeboxStatus

    @Throws(Exception::class)
    fun getShares(refresh: Boolean): List<Share>

    @Throws(Exception::class)
    fun getChatMessages(since: Long?): List<ChatMessage?>?

    @Throws(Exception::class)
    fun addChatMessage(message: String)

    @Throws(Exception::class)
    fun getBookmarks(): List<Bookmark>

    @Throws(Exception::class)
    fun deleteBookmark(id: String)

    @Throws(Exception::class)
    fun createBookmark(id: String, position: Int)

    @Throws(Exception::class)
    fun getVideos(refresh: Boolean): MusicDirectory?

    @Throws(Exception::class)
    fun getUser(username: String): UserInfo

    @Throws(Exception::class)
    fun createShare(ids: List<String>, description: String?, expires: Long?): List<Share>

    @Throws(Exception::class)
    fun deleteShare(id: String)

    @Throws(Exception::class)
    fun updateShare(id: String, description: String?, expires: Long?)

    @Throws(Exception::class)
    fun getPodcastEpisodes(podcastChannelId: String?): MusicDirectory?

    @Throws(Exception::class)
    fun mumaLogin()

    @Throws(Exception::class)
    fun getMumaTiles(): List<MumaTile>

    @Throws(Exception::class)
    fun saveMumaTile(tile: MumaTile): String

    @Throws(Exception::class)
    fun deleteMumaTile(id: String)

    @Throws(Exception::class)
    fun getMumaSettings(userId: Int, appId: String): String?

    @Throws(Exception::class)
    fun uploadCrashReport(
        deviceModel: String,
        osVersion: String,
        appVersionName: String,
        appVersionCode: Int,
        buildType: String,
        ringBufferText: String,
        stacktraceText: String?
    )

    @Throws(Exception::class)
    fun saveMumaSettings(userId: Int, appId: String, settings: String)
}
