/*
 * RESTMusicService.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.service

import java.io.IOException
import java.io.InputStream
import nl.teunschriks.mumamobile.api.muma.LoginRequest
import nl.teunschriks.mumamobile.api.muma.MumaTile as MumaApiTile
import nl.teunschriks.mumamobile.api.subsonic.ApiNotSupportedException
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.api.subsonic.models.JukeboxAction
import nl.teunschriks.mumamobile.api.subsonic.models.TrackForm
import nl.teunschriks.mumamobile.api.subsonic.throwOnFailure
import nl.teunschriks.mumamobile.api.subsonic.toStreamResponse
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.shouldUseId3Tags
import nl.teunschriks.mumamobile.data.SignOutEpoch
import nl.teunschriks.mumamobile.data.SubsonicSigning
import nl.teunschriks.mumamobile.data.isUsableMumaUserId
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
import nl.teunschriks.mumamobile.domain.OfflinePlaylist
import nl.teunschriks.mumamobile.domain.Playlist
import nl.teunschriks.mumamobile.domain.PodcastsChannel
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.SearchResult
import nl.teunschriks.mumamobile.domain.Share
import nl.teunschriks.mumamobile.domain.Tag
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.domain.UserInfo
import nl.teunschriks.mumamobile.domain.Year
import nl.teunschriks.mumamobile.domain.toArtistList
import nl.teunschriks.mumamobile.domain.toDomainEntitiesList
import nl.teunschriks.mumamobile.domain.toDomainEntity
import nl.teunschriks.mumamobile.domain.toDomainEntityList
import nl.teunschriks.mumamobile.domain.toIndexList
import nl.teunschriks.mumamobile.domain.toMusicDirectoryDomainEntity
import nl.teunschriks.mumamobile.domain.toTrackEntity
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.SecureSettings
import nl.teunschriks.mumamobile.util.Settings
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import timber.log.Timber

/**
 * This Music Service implementation connects to a server using the Subsonic REST API
 *
 * TooManyFunctions is suppressed on purpose: almost every function here is an override of
 * [MusicService], so the count is the size of that interface rather than of this class, and
 * CachedMusicService and OfflineMusicService implement the same surface.
 */
@Suppress("LargeClass", "TooManyFunctions")
open class RESTMusicService(
    private val subsonicAPIClient: SubsonicAPIClient,
    private val activeServerProvider: ActiveServerProvider
) : MusicService {

    // Shortcut to the API
    @Suppress("VariableNaming", "PropertyName")
    val API = subsonicAPIClient.api

    @Throws(Exception::class)
    override fun ping() {
        API.ping().execute().throwOnFailure()
        val activeServer = activeServerProvider.getActiveServer()
        if (activeServer.url.contains("example.com")) {
            ensureMumaLogin()
        }
    }

    @Throws(Exception::class)
    override fun isLicenseValid(): Boolean {
        val response = API.getLicense().execute().throwOnFailure()

        return response.body()!!.license.valid
    }

    @Throws(Exception::class)
    override fun getMusicFolders(refresh: Boolean): List<MusicFolder> {
        val response = API.getMusicFolders().execute().throwOnFailure()

        return response.body()!!.musicFolders.toDomainEntityList(activeServerId)
    }

    /**
     *  Retrieves the artists for a given music folder     *
     */
    @Throws(Exception::class)
    override fun getIndexes(musicFolderId: String?, refresh: Boolean): List<Index> {
        val response = API.getIndexes(musicFolderId, null).execute().throwOnFailure()

        return response.body()!!.indexes.toIndexList(
            ActiveServerProvider.getActiveServerId(),
            musicFolderId
        )
    }

    @Throws(Exception::class)
    override fun getArtists(
        refresh: Boolean,
        offset: Int?,
        count: Int?,
        query: String?,
        sortBy: String?
    ): List<Artist> {
        val response = API.getArtists(null, offset, count, query, sortBy).execute().throwOnFailure()

        return response.body()!!.indexes.toArtistList(activeServerId)
    }

    @Throws(Exception::class)
    override fun getArtistList(type: String, size: Int): List<Artist> {
        // role=release: without it the server returns every artist link, including remixers and
        // featured artists that have no albums of their own, whose detail screen is then empty.
        val response = API.getArtistList(type, size, 0, ROLE_RELEASE_ARTISTS)
            .execute()
            .throwOnFailure()

        return response.body()!!.artistList.map { it.toDomainEntity(activeServerId) }
    }

    @Throws(Exception::class)
    override fun getLabelList(type: String, size: Int): List<Label> {
        val response = API.getLabelList(type, size, 0).execute().throwOnFailure()

        return response.body()!!.labelList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getArtist(id: String): Artist? {
        val response = API.getArtist(id).execute().throwOnFailure()

        return response.body()!!.artist.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getArtistInfo(id: String): Artist? = try {
        val response = API.getArtistInfo2(id, null, null).execute().throwOnFailure()
        val info = response.body()!!.artistInfo
        Artist(
            id = id,
            serverId = activeServerId,
            genre = info.genre,
            description = info.biography
        )
    } catch (e: ApiNotSupportedException) {
        null
    }

    @Throws(Exception::class)
    override fun star(id: String?, albumId: String?, artistId: String?) {
        API.star(id, albumId, artistId).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun unstar(id: String?, albumId: String?, artistId: String?) {
        API.unstar(id, albumId, artistId).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun setRating(id: String, rating: Int) {
        API.setRating(id, rating).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun getMusicDirectory(id: String, name: String?, refresh: Boolean): MusicDirectory {
        val response = API.getMusicDirectory(id).execute().throwOnFailure()

        return response.body()!!.musicDirectory.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getAlbumsOfArtist(id: String, name: String?, refresh: Boolean): List<Album> {
        val response = API.getArtist(id).execute().throwOnFailure()

        return response.body()!!.artist.toDomainEntityList(activeServerId)
    }

    @Throws(Exception::class)
    override fun getAlbumAsDir(id: String, name: String?, refresh: Boolean): MusicDirectory {
        val response = API.getAlbum(id).execute().throwOnFailure()

        return response.body()!!.album.toMusicDirectoryDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getAlbum(id: String, name: String?, refresh: Boolean): Album {
        val response = API.getAlbum(id).execute().throwOnFailure()

        return response.body()!!.album.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getSingles(artistId: String, refresh: Boolean): MusicDirectory {
        val response = API.getSingles(artistId).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun search(criteria: SearchCriteria): SearchResult = try {
        if (shouldUseId3Tags()) {
            search3(criteria)
        } else {
            search2(criteria)
        }
    } catch (ignored: ApiNotSupportedException) {
        // Ensure backward compatibility with REST 1.3.
        searchOld(criteria)
    }

    /**
     * Search using the "search" REST method.
     */
    @Throws(Exception::class)
    private fun searchOld(criteria: SearchCriteria): SearchResult {
        val response =
            API.search(null, null, null, criteria.query, criteria.songCount, null, null)
                .execute().throwOnFailure()

        return response.body()!!.searchResult.toDomainEntity(activeServerId)
    }

    /**
     * Search using the "search2" REST method, available in 1.4.0 and later.
     */
    @Throws(Exception::class)
    private fun search2(criteria: SearchCriteria): SearchResult {
        requireNotNull(criteria.query) { "Query param is null" }
        val response = API.search2(
            criteria.query,
            criteria.artistCount,
            null,
            criteria.albumCount,
            null,
            criteria.songCount,
            null
        ).execute().throwOnFailure()

        return response.body()!!.searchResult.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    private fun search3(criteria: SearchCriteria): SearchResult {
        requireNotNull(criteria.query) { "Query param is null" }
        val response = API.search3(
            criteria.query,
            criteria.artistCount,
            null,
            criteria.albumCount,
            null,
            criteria.songCount,
            null
        ).execute().throwOnFailure()

        return response.body()!!.searchResult.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getPlaylist(id: String, name: String): MusicDirectory {
        val response = API.getPlaylist(id).execute().throwOnFailure()

        val playlist = response.body()!!.playlist.toMusicDirectoryDomainEntity(activeServerId)
        savePlaylist(name, playlist)
        cacheOfflinePlaylist(id, name, playlist)

        return playlist
    }

    @Throws(IOException::class)
    private fun savePlaylist(name: String, playlist: MusicDirectory) {
        val playlistFile = FileUtil.getPlaylistFile(
            activeServerProvider.getActiveServer().name,
            name
        )

        FileUtil.savePlaylist(playlistFile, playlist, name)
    }

    /**
     * Remembers this playlist's server id, name and track ids, so the offline shell's
     * `OfflineSubsonic` can answer `getPlaylists`/`getPlaylist` for it once the phone has no route
     * to the server. [savePlaylist] writes a `.m3u` file next to this that carries none of that --
     * see [OfflinePlaylist]'s class doc -- so the file alone cannot make an offline row become the
     * same row as its online one.
     *
     * Called from the one place both a plain view and a "download this playlist" go through, so
     * either is enough to keep the playlist reachable offline; there is no separate "download"
     * step for a playlist to hook into.
     */
    private fun cacheOfflinePlaylist(id: String, name: String, playlist: MusicDirectory) {
        activeServerProvider.getActiveMetaDatabase().offlinePlaylistDao().insert(
            OfflinePlaylist(
                id = id,
                serverId = activeServerId,
                name = name,
                trackIds = playlist.getTracks().map { it.id },
                updated = System.currentTimeMillis()
            )
        )
    }

    @Throws(Exception::class)
    override fun getPlaylists(refresh: Boolean): List<Playlist> {
        val response = API.getPlaylists(null).execute().throwOnFailure()

        return response.body()!!.playlists.toDomainEntitiesList()
    }

    /**
     * Either ID or String is required.
     * ID is required when updating
     * String is required when creating
     */
    @Throws(Exception::class)
    override fun createPlaylist(id: String?, name: String?, tracks: List<Track>) {
        require(id != null || name != null) { "Either id or name is required." }
        val pSongIds: MutableList<String> = ArrayList(tracks.size)

        for ((id1) in tracks) {
            pSongIds.add(id1)
        }

        API.createPlaylist(id, name, pSongIds.toList()).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun deletePlaylist(id: String) {
        API.deletePlaylist(id).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun updatePlaylist(id: String, name: String?, comment: String?, pub: Boolean) {
        API.updatePlaylist(id, name, comment, pub, null, null)
            .execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun getPodcastsChannels(refresh: Boolean): List<PodcastsChannel> {
        val response = API.getPodcasts(false, null).execute().throwOnFailure()

        return response.body()!!.podcastChannels.toDomainEntitiesList()
    }

    @Throws(Exception::class)
    override fun getPodcastEpisodes(podcastChannelId: String?): MusicDirectory {
        val response = API.getPodcasts(true, podcastChannelId).execute().throwOnFailure()

        val podcastEntries = response.body()!!.podcastChannels[0].episodeList
        val musicDirectory = MusicDirectory()

        for (podcastEntry in podcastEntries) {
            if (
                "skipped" != podcastEntry.status &&
                "error" != podcastEntry.status
            ) {
                val entry = podcastEntry.toTrackEntity(activeServerId)
                entry.track = null
                musicDirectory.add(entry)
            }
        }

        return musicDirectory
    }

    @Throws(Exception::class)
    override fun getLyrics(artist: String, title: String): Lyrics {
        val response = API.getLyrics(artist, title).execute().throwOnFailure()

        return response.body()!!.lyrics.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun scrobble(id: String, submission: Boolean, playedSeconds: Long?, source: String?, startedAtMs: Long?) {
        API.scrobble(id, startedAtMs, submission, playedSeconds, source).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun getAlbumList(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?
    ): List<Album> {
        val response = API.getAlbumList(
            type,
            size,
            offset,
            null,
            null,
            null,
            musicFolderId
        ).execute().throwOnFailure()

        return response.body()!!.albumList.toDomainEntityList(activeServerId)
    }

    @Throws(Exception::class)
    override fun getAlbumList2(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?,
        query: String?
    ): List<Album> {
        val response = API.getAlbumList2(
            type,
            size,
            offset,
            null,
            null,
            null,
            musicFolderId,
            query
        ).execute().throwOnFailure()

        return response.body()!!.albumList.toDomainEntityList(activeServerId)
    }

    @Throws(Exception::class)
    override fun getRandomSongs(size: Int): MusicDirectory {
        val response = API.getRandomSongs(
            size,
            null,
            null,
            null,
            null
        ).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun getStarred(): SearchResult {
        val response = API.getStarred(null).execute().throwOnFailure()

        return response.body()!!.starred.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getStarred2(): SearchResult {
        val response = API.getStarred2(null).execute().throwOnFailure()

        return response.body()!!.starred2.toDomainEntity(activeServerId)
    }

    @Throws(Exception::class)
    override fun getDownloadInputStream(
        song: Track,
        offset: Long,
        maxBitrate: Int,
        save: Boolean
    ): Pair<InputStream, Boolean> {
        val songOffset = if (offset < 0) 0 else offset

        // Use semantically correct call
        val response = if (save) {
            API.download(song.id, maxBitrate, offset = songOffset)
                .execute().toStreamResponse()
        } else {
            API.stream(song.id, maxBitrate, offset = songOffset)
                .execute().toStreamResponse()
        }

        response.throwOnFailure()

        if (response.stream == null) {
            throw IOException("Null stream response")
        }

        val partial = response.responseHttpCode == 206
        return Pair(response.stream!!, partial)
    }

    /**
     * We currently don't handle video playback in the app, but just create an Intent which video
     * players can respond to. For this intent we need the full URL of the stream, including the
     * authentication params. This is a bit tricky, because we want to avoid actually executing the
     * call because that could take a long time.
     */
    @Throws(Exception::class)
    override fun getStreamUrl(id: String, maxBitRate: Int?, format: String?): String {
        Timber.i("Start")

        // Get the request from Retrofit, but don't execute it!
        val request = API.stream(id).request()

        // Create a new call with the request, and execute ist on our custom client
        val response = streamClient.newCall(request).execute()

        // The complete url :)
        val url = response.request.url

        Timber.i("Done")

        return url.toString()
    }

    @Throws(Exception::class)
    override fun getTranscodedStreamUrl(
        id: String,
        maxBitRate: Int?,
        format: String?,
        timeOffset: Int?
    ): String {
        // Same trick as getStreamUrl: let Retrofit build the authenticated URL,
        // then intercept it instead of actually streaming. The difference is
        // that the transcoding parameters are passed through here.
        val request = API.stream(id, maxBitRate, format, timeOffset).request()
        val response = streamClient.newCall(request).execute()
        return response.request.url.toString()
    }

    private val streamClient by lazy {
        // Create a new modified okhttp client to intercept the URL
        val builder = subsonicAPIClient.okHttpClient.newBuilder()

        builder.addInterceptor { chain ->
            // Returns a dummy response
            Response.Builder()
                .code(100)
                .body("".toResponseBody(null))
                .protocol(Protocol.HTTP_2)
                .message("Empty response")
                .request(chain.request())
                .build()
        }

        // Create a new Okhttp client
        builder.build()
    }

    override fun isJukeboxAvailable(): Boolean {
        val username = activeServerProvider.getActiveServer().userName
        return getUser(username).jukeboxRole
    }

    @Throws(Exception::class)
    override fun updateJukeboxPlaylist(ids: List<String>): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.SET, null, null, ids, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun skipJukebox(index: Int, offsetSeconds: Int): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.SKIP, index, offsetSeconds, null, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun stopJukebox(): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.STOP, null, null, null, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun clearJukebox(): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.CLEAR, null, null, null, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun startJukebox(): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.START, null, null, null, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun getJukeboxStatus(): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.STATUS, null, null, null, null)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun setJukeboxGain(gain: Float): JukeboxStatus {
        val response = API.jukeboxControl(JukeboxAction.SET_GAIN, null, null, null, gain)
            .execute().throwOnFailure()

        return response.body()!!.jukebox.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun getShares(refresh: Boolean): List<Share> {
        val response = API.getShares().execute().throwOnFailure()

        return response.body()!!.shares.toDomainEntitiesList(activeServerId)
    }

    @Throws(Exception::class)
    override fun getGenres(refresh: Boolean, year: Int?, length: String?): List<Genre> {
        val response = API.getGenres(year, length).execute().throwOnFailure()

        return response.body()!!.genresList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getTags(refresh: Boolean, name: String, year: Int?, length: String?): List<Tag> {
        val response = API.getTags(name, year, length).execute().throwOnFailure()

        return response.body()!!.tagsList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getMemories(date: String): List<MemoryGroup> {
        val response = API.getMemories(date).execute().throwOnFailure()

        return response.body()!!.memoriesList.map {
            MemoryGroup(
                year = it.year,
                yearsAgo = it.yearsAgo,
                exact = it.exact,
                // The converter yields MusicDirectory.Child; only the playable ones are tracks,
                // the same narrowing MusicDirectory.getTracks() does.
                tracks = it.songs.toDomainEntityList(activeServerId).filterIsInstance<Track>()
            )
        }
    }

    @Throws(Exception::class)
    override fun getLineups(refresh: Boolean): List<Lineup> {
        val response = API.getLineups().execute().throwOnFailure()

        return response.body()!!.lineupList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getMoods(refresh: Boolean, year: Int?, length: String?): List<Mood> {
        val response = API.getMoods(year, length).execute().throwOnFailure()

        return response.body()!!.moodsList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getYears(refresh: Boolean): List<Year> {
        val response = API.getYears().execute().throwOnFailure()

        return response.body()!!.yearsList.toDomainEntityList()
    }

    @Throws(Exception::class)
    override fun getSongsByPath(paths: List<String>): MusicDirectory {
        // An empty feed is a normal answer, and asking the server to resolve nothing is not.
        if (paths.isEmpty()) return MusicDirectory()

        val response = API.getSongsByPath(paths).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun getSongsByGenre(
        genre: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory {
        val response = API.getSongsByGenre(
            genre,
            year,
            length,
            ratingMin,
            ratingMax,
            count,
            offset,
            null
        ).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun getSongs(
        filters: Filters,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int,
        sortMethod: String?,
        festivalLineup: String?,
        minDuration: Int?,
        maxDuration: Int?,
        artistIds: List<String>?,
        workId: Int?,
        canonicalOnly: Boolean?,
        forms: List<String>?,
        year: Int?
    ): MusicDirectory {
        Timber.d(filters.toString())

        val response = API.getSongs(
            if (filters.toString() == "") {
                null
            } else {
                filters.toString()
            },
            ratingMin,
            ratingMax,
            count,
            offset,
            null,
            sortMethod,
            festivalLineup,
            minDuration,
            maxDuration,
            artistIds?.takeIf { it.isNotEmpty() },
            workId,
            // Asking for one song's versions and collapsing to one of them are opposites, so
            // a workId always wins over the setting.
            if (workId != null) false else canonicalOnly ?: Settings.canonicalOnly,
            // The one place every caller's forms pass through: the server refuses an unknown
            // form for the whole request, so nothing it does not know ever leaves the app.
            TrackForm.sanitize(forms),
            year
        ).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))
        result.totalCount = response.body()!!.totalCount

        return result
    }

    @Throws(Exception::class)
    override fun getSongsByMood(
        mood: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory {
        val response = API.getSongsByMood(
            mood,
            year,
            length,
            ratingMin,
            ratingMax,
            count,
            offset,
            null
        ).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun getSongsByYear(
        year: Int,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory {
        val response = API.getSongsByYear(
            year,
            length,
            ratingMin,
            ratingMax,
            count,
            offset,
            null
        ).execute().throwOnFailure()

        val result = MusicDirectory()
        result.addAll(response.body()!!.songsList.toDomainEntityList(activeServerId))

        return result
    }

    @Throws(Exception::class)
    override fun getUser(username: String): UserInfo {
        val response = API.getUser(username).execute().throwOnFailure()

        return response.body()!!.user.toDomainEntity()
    }

    @Throws(Exception::class)
    override fun getChatMessages(since: Long?): List<ChatMessage> {
        val response = API.getChatMessages(since).execute().throwOnFailure()

        return response.body()!!.chatMessages.toDomainEntitiesList()
    }

    @Throws(Exception::class)
    override fun addChatMessage(message: String) {
        API.addChatMessage(message).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun getBookmarks(): List<Bookmark> {
        val response = API.getBookmarks().execute().throwOnFailure()

        return response.body()!!.bookmarkList.toDomainEntitiesList(activeServerId)
    }

    @Throws(Exception::class)
    override fun createBookmark(id: String, position: Int) {
        API.createBookmark(id, position.toLong(), null).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun deleteBookmark(id: String) {
        API.deleteBookmark(id).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun getVideos(refresh: Boolean): MusicDirectory {
        val response = API.getVideos().execute().throwOnFailure()

        val musicDirectory = MusicDirectory()
        musicDirectory.addAll(response.body()!!.videosList.toDomainEntityList(activeServerId))

        return musicDirectory
    }

    @Throws(Exception::class)
    override fun createShare(ids: List<String>, description: String?, expires: Long?): List<Share> {
        val response = API.createShare(ids, description, expires).execute().throwOnFailure()

        return response.body()!!.shares.toDomainEntitiesList(activeServerId)
    }

    @Throws(Exception::class)
    override fun deleteShare(id: String) {
        API.deleteShare(id).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun updateShare(id: String, description: String?, expires: Long?) {
        var expiresValue: Long? = expires
        if (expires != null && expires == 0L) {
            expiresValue = null
        }

        API.updateShare(id, description, expiresValue).execute().throwOnFailure()
    }

    @Throws(Exception::class)
    override fun mumaLogin() {
        ensureMumaLogin(force = true)
    }

    /**
     * Asks MuMa for the signed-in user's Subsonic API token and stores it in [SecureSettings]; see
     * [MusicService.refreshSubsonicToken] and [SubsonicSigning]. A refusal (401/403, or 404 for an
     * account no server knows yet) returns `false`, an outage (5xx, 429, no network) throws; both
     * leave the stored state alone, so the client keeps signing with whatever token it had -- and
     * sends nothing when it had none (issue #72). The token is never logged.
     */
    @Throws(Exception::class)
    override fun refreshSubsonicToken(): Boolean {
        val activeServer = activeServerProvider.getActiveServer()
        if (activeServer.userName.isEmpty() || activeServer.password.isEmpty()) return false
        val epoch = SignOutEpoch.current()
        ensureMumaLogin()
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.getSubsonicToken().execute() }
        if (!response.isSuccessful) {
            val code = response.code()
            response.errorBody()?.close()
            // A refusal (401/403: the key or the account; 404: no server knows the account yet)
            // means "sign in again"; anything else -- a 5xx, a 429 -- that the server is not
            // answering for now. The difference is what the listener is told when no token can be
            // had and requests are therefore not sent (issue #72).
            if (MumaLoginRefusedException.isRefusal(code)) {
                Timber.w("Subsonic token refused (HTTP %d); requests keep their current token", code)
                return false
            }
            Timber.w("Subsonic token not available (HTTP %d); requests keep their current token", code)
            throw IOException("Subsonic token endpoint answered HTTP $code")
        }
        val body = response.body()
        // A sign-out while the request was out must win: storing the answer now would put a
        // credential back that the sign-out just cleared (bug report 106).
        if (activeServerProvider.getActiveServer().password.isEmpty()) {
            Timber.i("Signed out while the Subsonic token was being fetched; answer dropped")
            return false
        }
        val adoption = SubsonicSigning.adopt(
            storedUserName = activeServerProvider.getActiveServer().userName,
            storedToken = SecureSettings.subsonicToken,
            storedTokenUser = SecureSettings.subsonicTokenUser,
            answerUserName = body?.username,
            answerToken = body?.token
        )
        return when (adoption) {
            is SubsonicSigning.Adoption.Store -> {
                // The check above leaves a gap before the write, and misses a sign-out followed by
                // a new sign-in; the epoch closes both (bug report 111).
                val stored = SignOutEpoch.storeIfUnchanged(epoch) {
                    adoption.canonicalUserName?.let { activeServerProvider.adoptCanonicalUserName(it) }
                    SecureSettings.subsonicToken = adoption.token
                    SecureSettings.subsonicTokenUser = adoption.tokenUser
                }
                if (stored) {
                    Timber.i("Subsonic token stored; requests are signed with it from now on")
                } else {
                    Timber.i("Signed out while the Subsonic token was being fetched; answer dropped")
                }
                stored
            }
            SubsonicSigning.Adoption.Unchanged -> false
            SubsonicSigning.Adoption.Ignore -> {
                Timber.w("Subsonic token answer was not for this account; ignored")
                false
            }
        }
    }

    /**
     * Makes sure the MuMa client carries an API key, logging in with the Subsonic credentials
     * only when no key is stored yet or when [force] says the stored one was refused.
     *
     * The stored key lives in [Settings.mumaApiKey] (written by
     * [ActiveServerProvider.setMumaSettings]); the server entry's own `apiKey` is never filled
     * for the static servers. Reading only the latter made every settings, tile and crash-report
     * call post `/api/auth/login` first, which is what fed the login rate limit.
     */
    @Throws(Exception::class)
    private fun ensureMumaLogin(force: Boolean = false) {
        val activeServer = activeServerProvider.getActiveServer()
        val credentials = MumaStoredCredentials.resolve(
            serverApiKey = activeServer.apiKey,
            serverUserId = activeServer.mumaUserId,
            settingsApiKey = Settings.mumaApiKey,
            settingsUserId = Settings.mumaUserId
        )
        if (!force && credentials != null) {
            subsonicAPIClient.mumaApi.setApiKey(credentials.apiKey)
            return
        }

        if (activeServer.userName.isEmpty() || activeServer.password.isEmpty()) {
            return
        }

        Timber.i("MuMa API key missing or logon forced, attempting login with Subsonic credentials")
        val req = LoginRequest(activeServer.userName, activeServer.password)
        val response = subsonicAPIClient.mumaApi.api.login(req).execute()

        if (response.isSuccessful) {
            val body = response.body()
            if (body != null) {
                val apiKey = body.apiKey ?: body.accessToken
                    ?: throw IOException("MuMa login returned no API key")
                // The account id is nested under "user". Reading it flat left it at Gson's default
                // of 0, which is not the "unknown" sentinel, so every per-user call afterwards went
                // to /api/users/0/... -- settings saves answered 500 on a foreign key violation.
                val userId = body.user?.id
                if (userId == null) {
                    Timber.w("MuMa login returned no account id; leaving the stored id untouched")
                }
                activeServerProvider.setMumaSettings(apiKey, userId)
                subsonicAPIClient.mumaApi.setApiKey(apiKey)
                // Sign in under the account's own spelling from now on, not the typed one: LMS
                // created a second user for a case variant (bug report 074).
                MumaStoredCredentials.canonicalUserName(activeServer.userName, body.user?.username)
                    ?.let { activeServerProvider.adoptCanonicalUserName(it) }
                Timber.i("MuMa login successful")
            }
        } else {
            val code = response.code()
            Timber.e("MuMa login failed: $code")
            throw if (MumaLoginRefusedException.isRefusal(code)) MumaLoginRefusedException(code) else IOException("MuMa login failed: $code")
        }
    }

    /**
     * Runs [request] and, when the server answers 401 to the stored key, logs in once and runs
     * it again. Now that a stored key is trusted instead of re-validated by a login on every
     * call, this is what recovers from a key the server no longer accepts.
     */
    @Throws(Exception::class)
    private fun <T> retryOnceWhenUnauthorized(request: () -> retrofit2.Response<T>): retrofit2.Response<T> = MumaStoredCredentials.retryOnceWhenUnauthorized(
        login = { ensureMumaLogin(force = true) },
        request = request
    )

    @Throws(Exception::class)
    override fun getMumaTiles(): List<MumaTile> {
        ensureMumaLogin()
        val activeServer = activeServerProvider.getActiveServer()
        val userId = activeServer.mumaUserId ?: Settings.mumaUserId
        if (!isUsableMumaUserId(userId)) throw IOException("User ID not set")

        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.getTiles(userId).execute() }
        if (!response.isSuccessful) throw IOException("Failed to get MuMa tiles: ${response.code()}")
        return response.body()?.map { MumaTile(it.id?.toString(), it.name, it.smartParams) } ?: emptyList()
    }

    @Throws(Exception::class)
    override fun saveMumaTile(tile: MumaTile): String {
        ensureMumaLogin()
        val activeServer = activeServerProvider.getActiveServer()
        val userId = activeServer.mumaUserId ?: Settings.mumaUserId
        if (!isUsableMumaUserId(userId)) throw IOException("User ID not set")

        val apiTile = MumaApiTile(tile.id?.toIntOrNull(), tile.name, tile.smartParams)
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.saveTile(userId, apiTile).execute() }
        if (!response.isSuccessful) throw IOException("Failed to save MuMa tile: ${response.code()}")
        return response.body()?.id ?: throw IOException("Empty response from server")
    }

    @Throws(Exception::class)
    override fun deleteMumaTile(id: String) {
        ensureMumaLogin()
        val activeServer = activeServerProvider.getActiveServer()
        val userId = activeServer.mumaUserId ?: Settings.mumaUserId
        if (!isUsableMumaUserId(userId)) throw IOException("User ID not set")

        val playlistId = id.toIntOrNull() ?: throw IOException("Invalid tile ID: $id")
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.deleteTile(userId, playlistId).execute() }
        if (!response.isSuccessful) throw IOException("Failed to delete MuMa tile: ${response.code()}")
    }

    @Throws(Exception::class)
    override fun getMumaSettings(userId: Int, appId: String): String? {
        ensureMumaLogin()
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.getSettings(userId, appId).execute() }
        if (!response.isSuccessful) throw IOException("Failed to get settings: ${response.code()}")
        return response.body()?.settings
    }

    @Throws(Exception::class)
    override fun saveMumaSettings(userId: Int, appId: String, settings: String) {
        ensureMumaLogin()
        val req = nl.teunschriks.mumamobile.api.muma.MumaSettingsRequest(settings)
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.saveSettings(userId, appId, req).execute() }
        if (!response.isSuccessful) throw IOException("Failed to save settings: ${response.code()}")
    }

    /**
     * A per-key `PATCH`. A server from before it answers 405; only then does this fall back to the
     * old read-merge-write, which can still lose another device's write made in between.
     */
    @Throws(Exception::class)
    override fun patchMumaSettings(userId: Int, appId: String, changes: String) {
        ensureMumaLogin()
        val req = nl.teunschriks.mumamobile.api.muma.MumaSettingsPatchRequest(settingsChangesObject(changes))
        val response = retryOnceWhenUnauthorized {
            subsonicAPIClient.mumaApi.api.patchSettings(userId, appId, req).execute()
        }
        if (response.code() == HTTP_METHOD_NOT_ALLOWED) {
            saveMumaSettings(userId, appId, mergeSettingsChanges(getMumaSettings(userId, appId), changes))
            return
        }
        if (!response.isSuccessful) throw IOException("Failed to patch settings: ${response.code()}")
    }

    @Throws(Exception::class)
    override fun uploadCrashReport(
        deviceModel: String,
        osVersion: String,
        appVersionName: String,
        appVersionCode: Int,
        buildType: String,
        ringBufferText: String,
        stacktraceText: String?
    ) {
        ensureMumaLogin()
        val req = nl.teunschriks.mumamobile.api.muma.CrashReportRequest(
            deviceModel = deviceModel,
            osVersion = osVersion,
            appVersionName = appVersionName,
            appVersionCode = appVersionCode,
            buildType = buildType,
            ringBufferText = ringBufferText,
            stacktraceText = stacktraceText
        )
        val response = retryOnceWhenUnauthorized { subsonicAPIClient.mumaApi.api.uploadCrashReport(req).execute() }
        if (!response.isSuccessful) throw IOException("Failed to upload crash report: ${response.code()}")
    }

    private val activeServerId: Int
        get() = ActiveServerProvider.getActiveServerId()

    init {
        // The client will notice if the minimum supported API version has changed
        // By registering a callback we ensure this info is saved in the database as well
        subsonicAPIClient.onProtocolChange = {
            Timber.i("Server minimum API version set to %s", it)
            activeServerProvider.setMinimumApiVersion(it.restApiVersion)
        }
    }

    companion object {
        /** getArtistList role that keeps track-only artists (remixers, features) out of the list. */
        private const val ROLE_RELEASE_ARTISTS = "release"
    }
}

/** What a server without the per-key settings `PATCH` answers it with. */
private const val HTTP_METHOD_NOT_ALLOWED = 405
