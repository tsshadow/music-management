/*
 * CachedMusicService.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */
package nl.teunschriks.mumamobile.service

import java.io.InputStream
import java.util.concurrent.TimeUnit
import kotlin.Pair
import nl.teunschriks.mumamobile.api.subsonic.models.AlbumListType
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.MetaDatabase
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
import nl.teunschriks.mumamobile.util.LRUCache
import nl.teunschriks.mumamobile.util.MediaItemConverter
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.TimeLimitedCache
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject

@Suppress("TooManyFunctions")
class CachedMusicService(private val musicService: MusicService) :
    MusicService,
    KoinComponent {
    private val activeServerProvider: ActiveServerProvider by inject()
    private var metaDatabase: MetaDatabase = activeServerProvider.getActiveMetaDatabase()

    // Old style TimeLimitedCache
    private var cachedMusicDirectories: LRUCache<String, TimeLimitedCache<MusicDirectory?>>
    private var cachedAlbum: LRUCache<String, TimeLimitedCache<MusicDirectory?>>
    private var cachedUserInfo: LRUCache<String, TimeLimitedCache<UserInfo?>>
    private val cachedLicenseValid = TimeLimitedCache<Boolean>(120, TimeUnit.SECONDS)
    private val cachedPlaylists = TimeLimitedCache<List<Playlist>?>(3600, TimeUnit.SECONDS)
    private val cachedPodcastsChannels =
        TimeLimitedCache<List<PodcastsChannel>?>(3600, TimeUnit.SECONDS)
    private val cachedGenres = TimeLimitedCache<List<Genre>>(10 * 3600, TimeUnit.SECONDS)
    private val cachedLineups = TimeLimitedCache<List<Lineup>>(10 * 3600, TimeUnit.SECONDS)
    private val cachedMoods = TimeLimitedCache<List<Mood>>(10 * 3600, TimeUnit.SECONDS)
    private val cachedYears = TimeLimitedCache<List<Year>>(10 * 3600, TimeUnit.SECONDS)

    // New multi-key cache for getTags, allowing separation by (name, year, length)
    private val cachedTagsMap: MutableMap<String, TimeLimitedCache<List<Tag>>> = mutableMapOf()

    // Home screen lists, keyed by "<kind>-<type>-<size>" (see cachedHomeList)
    private val cachedHomeLists: MutableMap<String, TimeLimitedCache<List<Any>>> = mutableMapOf()

    // Single artists by id (see getArtist)
    private val cachedArtist: MutableMap<String, TimeLimitedCache<Artist?>> = mutableMapOf()

    // Room Database
    private var cachedArtists = metaDatabase.artistDao()
    private var cachedAlbums = metaDatabase.albumDao()
    private var cachedIndexes = metaDatabase.indexDao()
    private val cachedMusicFolders = metaDatabase.musicFoldersDao()

    private var restUrl: String? = null
    private var cachedMusicFolderId: String? = null

    init {
        cachedMusicDirectories = LRUCache(MUSIC_DIR_CACHE_SIZE)
        cachedAlbum = LRUCache(MUSIC_DIR_CACHE_SIZE)
        cachedUserInfo = LRUCache(MUSIC_DIR_CACHE_SIZE)
    }

    /**
     * Helper to build a unique cache key based on tag parameters.
     */
    private fun buildTagCacheKey(name: String, year: Int?, length: String?): String = listOf(name, year?.toString() ?: "", length ?: "").joinToString("_")

    @Throws(Exception::class)
    override fun ping() {
        checkSettingsChanged()
        musicService.ping()
    }

    @Throws(Exception::class)
    override fun isLicenseValid(): Boolean {
        checkSettingsChanged()
        var isValid = cachedLicenseValid.get()
        if (isValid == null) {
            isValid = musicService.isLicenseValid()
            cachedLicenseValid.set(isValid)
        }
        return isValid
    }

    @Throws(Exception::class)
    override fun getMusicFolders(refresh: Boolean): List<MusicFolder> {
        checkSettingsChanged()
        if (refresh) {
            cachedMusicFolders.clear()
        }
        var result = cachedMusicFolders.get()

        if (result.isEmpty()) {
            result = musicService.getMusicFolders(refresh)
            cachedMusicFolders.set(result)
        }
        return result
    }

    @Throws(Exception::class)
    override fun getIndexes(musicFolderId: String?, refresh: Boolean): List<Index> {
        checkSettingsChanged()

        if (refresh) {
            cachedIndexes.clear()
            cachedMusicDirectories.clear()
        }

        var indexes: List<Index>

        indexes = if (musicFolderId == null) {
            cachedIndexes.get()
        } else {
            cachedIndexes.get(musicFolderId)
        }

        if (indexes.isEmpty()) {
            indexes = musicService.getIndexes(musicFolderId, refresh)
            cachedIndexes.upsert(indexes)
        }

        return indexes
    }

    @Throws(Exception::class)
    override fun getArtists(
        refresh: Boolean,
        offset: Int?,
        count: Int?,
        query: String?,
        sortBy: String?
    ): List<Artist> {
        checkSettingsChanged()

        if (artistsCacheBypassesFor(query, sortBy, count)) {
            return musicService.getArtists(refresh, offset, count, query, sortBy)
        }

        if (refresh) {
            cachedArtists.clear()
        }

        var result = cachedArtists.get()

        if (result.isEmpty()) {
            result = musicService.getArtists(refresh, offset, count, query, sortBy)
            cachedArtists.set(result)
        }
        return result
    }

    @Throws(Exception::class)
    @Suppress("UNCHECKED_CAST")
    override fun getArtistList(type: String, size: Int): List<Artist> {
        checkSettingsChanged()

        return cachedHomeList("artist-$type-$size") {
            musicService.getArtistList(type, size)
        } as List<Artist>
    }

    @Throws(Exception::class)
    @Suppress("UNCHECKED_CAST")
    override fun getLabelList(type: String, size: Int): List<Label> {
        checkSettingsChanged()

        return cachedHomeList("label-$type-$size") {
            musicService.getLabelList(type, size)
        } as List<Label>
    }

    // The home screen should notice new music well before the ten-hour genre/tag caches would.
    private fun cachedHomeList(key: String, loader: () -> List<Any>): List<Any> {
        cachedHomeLists[key]?.get()?.let { return it }

        val result = loader()
        val cache = TimeLimitedCache<List<Any>>(HOME_LIST_CACHE_SECONDS, TimeUnit.SECONDS)
        cache.set(result)
        cachedHomeLists[key] = cache
        return result
    }

    /**
     * Cached because the shortcuts grid asks for the same handful of artists on every visit to
     * the home screen, purely to fill in artwork it has no other source for.
     */
    @Throws(Exception::class)
    override fun getArtist(id: String): Artist? {
        checkSettingsChanged()

        cachedArtist[id]?.get()?.let { return it }

        val artist = musicService.getArtist(id) ?: return null
        val cache = TimeLimitedCache<Artist?>(ARTIST_CACHE_SECONDS, TimeUnit.SECONDS)
        cache.set(artist)
        cachedArtist[id] = cache
        return artist
    }

    @Throws(Exception::class)
    override fun getArtistInfo(id: String): Artist? = musicService.getArtistInfo(id)

    @Throws(Exception::class)
    override fun getMusicDirectory(id: String, name: String?, refresh: Boolean): MusicDirectory {
        checkSettingsChanged()
        var cache = if (refresh) null else cachedMusicDirectories[id]
        var dir = cache?.get()
        if (dir == null) {
            dir = musicService.getMusicDirectory(id, name, refresh)
            cache = TimeLimitedCache(
                Settings.directoryCacheTime.toLong(),
                TimeUnit.SECONDS
            )
            cache.set(dir)
            cachedMusicDirectories.put(id, cache)
        }
        return dir
    }

    /*
     * Retrieves all albums of the provided artist.
     * Cached in the RoomDB
     */
    @Throws(Exception::class)
    override fun getAlbumsOfArtist(id: String, name: String?, refresh: Boolean): List<Album> {
        checkSettingsChanged()

        var result: List<Album>

        result = if (refresh) {
            cachedAlbums.clearByArtist(id)
            listOf()
        } else {
            cachedAlbums.byArtist(id)
        }

        if (result.isEmpty()) {
            result = musicService.getAlbumsOfArtist(id, name, refresh)
            cachedAlbums.upsert(result)
        }
        return result
    }

    @Throws(Exception::class)
    override fun getAlbumAsDir(id: String, name: String?, refresh: Boolean): MusicDirectory {
        checkSettingsChanged()
        var cache = if (refresh) null else cachedAlbum[id]
        var dir = cache?.get()
        if (dir == null) {
            dir = musicService.getAlbumAsDir(id, name, refresh)
            cache = TimeLimitedCache(
                Settings.directoryCacheTime.toLong(),
                TimeUnit.SECONDS
            )
            cache.set(dir)
            cachedAlbum.put(id, cache)
        }
        return dir
    }

    @Throws(Exception::class)
    override fun getAlbum(id: String, name: String?, refresh: Boolean): Album? {
        checkSettingsChanged()
        var cache = if (refresh) null else cachedAlbums.get(id)
        if (cache == null) {
            try {
                cache = musicService.getAlbum(id, name, refresh)
            } catch (ignored: Exception) {
            }

            cache?.let { cachedAlbums.upsert(it) }
        }
        return cache
    }

    override fun getSingles(artistId: String, refresh: Boolean): MusicDirectory = musicService.getSingles(artistId, refresh)

    @Throws(Exception::class)
    override fun search(criteria: SearchCriteria): SearchResult? = musicService.search(criteria)

    @Throws(Exception::class)
    override fun getPlaylist(id: String, name: String): MusicDirectory = musicService.getPlaylist(id, name)

    @Throws(Exception::class)
    override fun getPodcastsChannels(refresh: Boolean): List<PodcastsChannel> {
        checkSettingsChanged()
        var result = if (refresh) null else cachedPodcastsChannels.get()
        if (result == null) {
            result = musicService.getPodcastsChannels(refresh)
            cachedPodcastsChannels.set(result)
        }
        return result
    }

    @Throws(Exception::class)
    override fun getPodcastEpisodes(podcastChannelId: String?): MusicDirectory? = musicService.getPodcastEpisodes(podcastChannelId)

    @Throws(Exception::class)
    override fun mumaLogin() {
        musicService.mumaLogin()
    }

    @Throws(Exception::class)
    override fun getPlaylists(refresh: Boolean): List<Playlist> {
        checkSettingsChanged()
        var result = if (refresh) null else cachedPlaylists.get()
        if (result == null) {
            result = musicService.getPlaylists(refresh)
            cachedPlaylists.set(result)
        }
        return result
    }

    @Throws(Exception::class)
    override fun createPlaylist(id: String?, name: String?, tracks: List<Track>) {
        cachedPlaylists.clear()
        musicService.createPlaylist(id, name, tracks)
    }

    @Throws(Exception::class)
    override fun deletePlaylist(id: String) {
        musicService.deletePlaylist(id)
    }

    @Throws(Exception::class)
    override fun updatePlaylist(id: String, name: String?, comment: String?, pub: Boolean) {
        musicService.updatePlaylist(id, name, comment, pub)
    }

    @Throws(Exception::class)
    override fun getLyrics(artist: String, title: String): Lyrics? = musicService.getLyrics(artist, title)

    @Throws(Exception::class)
    override fun scrobble(id: String, submission: Boolean, playedSeconds: Long?, source: String?) {
        musicService.scrobble(id, submission, playedSeconds, source)
    }

    @Throws(Exception::class)
    override fun getAlbumList(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?
    ): List<Album> = musicService.getAlbumList(type, size, offset, musicFolderId)

    @Throws(Exception::class)
    override fun getAlbumList2(
        type: AlbumListType,
        size: Int,
        offset: Int,
        musicFolderId: String?,
        query: String?
    ): List<Album> = musicService.getAlbumList2(type, size, offset, musicFolderId, query)

    @Throws(Exception::class)
    override fun getRandomSongs(size: Int): MusicDirectory = musicService.getRandomSongs(size)

    @Throws(Exception::class)
    override fun getStarred(): SearchResult = musicService.getStarred()

    @Throws(Exception::class)
    override fun getStarred2(): SearchResult = musicService.getStarred2()

    @Throws(Exception::class)
    override fun getDownloadInputStream(
        song: Track,
        offset: Long,
        maxBitrate: Int,
        save: Boolean
    ): Pair<InputStream, Boolean> = musicService.getDownloadInputStream(song, offset, maxBitrate, save)

    @Throws(Exception::class)
    override fun getStreamUrl(id: String, maxBitRate: Int?, format: String?): String? = musicService.getStreamUrl(id, maxBitRate, format)

    override fun getTranscodedStreamUrl(id: String, maxBitRate: Int?, format: String?, timeOffset: Int?): String? = musicService.getTranscodedStreamUrl(id, maxBitRate, format, timeOffset)

    override fun isJukeboxAvailable(): Boolean = musicService.isJukeboxAvailable()

    @Throws(Exception::class)
    override fun updateJukeboxPlaylist(ids: List<String>): JukeboxStatus = musicService.updateJukeboxPlaylist(ids)

    @Throws(Exception::class)
    override fun skipJukebox(index: Int, offsetSeconds: Int): JukeboxStatus = musicService.skipJukebox(index, offsetSeconds)

    @Throws(Exception::class)
    override fun stopJukebox(): JukeboxStatus = musicService.stopJukebox()

    @Throws(Exception::class)
    override fun clearJukebox(): JukeboxStatus = musicService.clearJukebox()

    @Throws(Exception::class)
    override fun startJukebox(): JukeboxStatus = musicService.startJukebox()

    @Throws(Exception::class)
    override fun getJukeboxStatus(): JukeboxStatus = musicService.getJukeboxStatus()

    @Throws(Exception::class)
    override fun setJukeboxGain(gain: Float): JukeboxStatus = musicService.setJukeboxGain(gain)

    @Synchronized
    private fun checkSettingsChanged() {
        val newUrl = activeServerProvider.getRestUrl(null)
        val newFolderId = activeServerProvider.getActiveServer().musicFolderId
        if (newUrl != restUrl || cachedMusicFolderId != newFolderId) {
            // Switch database
            metaDatabase = activeServerProvider.getActiveMetaDatabase()
            cachedArtists = metaDatabase.artistDao()
            cachedAlbums = metaDatabase.albumDao()
            cachedIndexes = metaDatabase.indexDao()

            // Clear in memory caches
            cachedMusicDirectories.clear()
            cachedLicenseValid.clear()
            cachedPlaylists.clear()
            cachedGenres.clear()
            cachedAlbum.clear()
            cachedUserInfo.clear()
            cachedHomeLists.clear()
            cachedArtist.clear()

            // Set the cache keys
            restUrl = newUrl
            cachedMusicFolderId = newFolderId
        }
    }

    @Throws(Exception::class)
    override fun star(id: String?, albumId: String?, artistId: String?) {
        musicService.star(id, albumId, artistId)
    }

    @Throws(Exception::class)
    override fun unstar(id: String?, albumId: String?, artistId: String?) {
        musicService.unstar(id, albumId, artistId)
    }

    /**
     * The server is told first; the cached copies of the track are corrected after, so that a
     * rating set in the car or on a list is the one the app reports back until the cache is
     * refetched. See [applyRatingToCachedTracks].
     */
    @Throws(Exception::class)
    override fun setRating(id: String, rating: Int) {
        musicService.setRating(id, rating)

        for (dir in cachedMusicDirectories.values() + cachedAlbum.values()) {
            applyRatingToCachedTracks(dir, id, rating)
        }
        for (list in cachedHomeLists.values) {
            applyRatingToCachedTracks(list.get(), id, rating)
        }
        MediaItemConverter.applyRating(id, rating)
    }

    @Throws(Exception::class)
    override fun getGenres(refresh: Boolean, year: Int?, length: String?): List<Genre> {
        checkSettingsChanged()
        if (refresh) {
            cachedGenres.clear()
        }
        var result = cachedGenres.get()
        if (result == null) {
            result = musicService.getGenres(refresh, year, length)
            cachedGenres.set(result)
        }

        val sorted = result.toMutableList()
        sorted.sortWith { genre, genre2 ->
            genre.name.compareTo(
                genre2.name,
                ignoreCase = true
            )
        }
        return sorted
    }

    @Throws(Exception::class)
    override fun getTags(refresh: Boolean, name: String, year: Int?, length: String?): List<Tag> {
        checkSettingsChanged()

        val cacheKey = buildTagCacheKey(name, year, length)
        val cache = if (refresh) null else cachedTagsMap[cacheKey]
        var result = cache?.get()

        if (result == null) {
            result = musicService.getTags(refresh, name, year, length)
            val newCache = TimeLimitedCache<List<Tag>>(10 * 3600, TimeUnit.SECONDS)
            newCache.set(result)
            cachedTagsMap[cacheKey] = newCache
        }

        val sorted = result.toMutableList()
        sorted.sortWith { tag, tag2 ->
            tag.name.compareTo(tag2.name, ignoreCase = true)
        }
        return sorted
    }

    @Throws(Exception::class)
    // Deliberately uncached: the answer changes every day, and it is one request per screen.
    override fun getMemories(date: String): List<MemoryGroup> = musicService.getMemories(date)

    override fun getLineups(refresh: Boolean): List<Lineup> {
        checkSettingsChanged()
        if (refresh) {
            cachedLineups.clear()
        }
        var result = cachedLineups.get()
        if (result == null) {
            result = musicService.getLineups(refresh)
            cachedLineups.set(result)
        }
        return result
    }

    @Throws(Exception::class)
    override fun getMoods(refresh: Boolean, year: Int?, length: String?): List<Mood> {
        checkSettingsChanged()
        if (refresh) {
            cachedMoods.clear()
        }
        var result = cachedMoods.get()
        if (result == null) {
            result = musicService.getMoods(refresh, year, length)
            cachedMoods.set(result)
        }

        val sorted = result.toMutableList()
        sorted.sortWith { mood, mood2 ->
            mood.name.compareTo(
                mood2.name,
                ignoreCase = true
            )
        }
        return sorted
    }

    @Throws(Exception::class)
    override fun getYears(refresh: Boolean): List<Year> {
        checkSettingsChanged()
        if (refresh) {
            cachedYears.clear()
        }
        var result = cachedYears.get()
        if (result == null) {
            result = musicService.getYears(refresh)
            cachedYears.set(result)
        }

        val sorted = result.toMutableList()
        sorted.sortWith { Year, Year2 ->
            Year.name.compareTo(
                Year2.name,
                ignoreCase = true
            )
        }
        return sorted
    }

    // Not cached: a feed is rebuilt server-side every day, and a cache under it would hand
    // back yesterday's radar while the screen above it says today's.
    @Throws(Exception::class)
    override fun getSongsByPath(paths: List<String>): MusicDirectory = musicService.getSongsByPath(paths)

    @Throws(Exception::class)
    override fun getSongsByGenre(
        genre: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory = musicService.getSongsByGenre(
        genre,
        year,
        length,
        ratingMin,
        ratingMax,
        count,
        offset
    )

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
        canonicalOnly: Boolean?
    ): MusicDirectory = musicService.getSongs(
        filters,
        ratingMin,
        ratingMax,
        count,
        offset,
        sortMethod,
        festivalLineup,
        minDuration,
        maxDuration,
        artistIds,
        workId,
        canonicalOnly
    )

    @Throws(Exception::class)
    override fun getSongsByMood(
        mood: String,
        year: Int?,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory = musicService.getSongsByMood(mood, year, length, ratingMin, ratingMax, count, offset)

    @Throws(Exception::class)
    override fun getSongsByYear(
        year: Int,
        length: String?,
        ratingMin: Int?,
        ratingMax: Int?,
        count: Int,
        offset: Int
    ): MusicDirectory = musicService.getSongsByYear(year, length, ratingMin, ratingMax, count, offset)

    @Throws(Exception::class)
    override fun getShares(refresh: Boolean): List<Share> = musicService.getShares(refresh)

    @Throws(Exception::class)
    override fun getChatMessages(since: Long?): List<ChatMessage?>? = musicService.getChatMessages(since)

    @Throws(Exception::class)
    override fun addChatMessage(message: String) {
        musicService.addChatMessage(message)
    }

    @Throws(Exception::class)
    override fun getBookmarks(): List<Bookmark> = musicService.getBookmarks()

    @Throws(Exception::class)
    override fun deleteBookmark(id: String) {
        musicService.deleteBookmark(id)
    }

    @Throws(Exception::class)
    override fun createBookmark(id: String, position: Int) {
        musicService.createBookmark(id, position)
    }

    @Throws(Exception::class)
    override fun getVideos(refresh: Boolean): MusicDirectory? {
        checkSettingsChanged()
        var cache =
            if (refresh) null else cachedMusicDirectories[CACHE_KEY_VIDEOS]
        var dir = cache?.get()
        if (dir == null) {
            dir = musicService.getVideos(refresh)
            cache = TimeLimitedCache(
                Settings.directoryCacheTime.toLong(),
                TimeUnit.SECONDS
            )
            cache.set(dir)
            cachedMusicDirectories.put(CACHE_KEY_VIDEOS, cache)
        }
        return dir
    }

    @Throws(Exception::class)
    override fun getUser(username: String): UserInfo {
        checkSettingsChanged()
        var cache = cachedUserInfo[username]
        var userInfo = cache?.get()
        if (userInfo == null) {
            userInfo = musicService.getUser(username)
            cache = TimeLimitedCache(
                Settings.directoryCacheTime.toLong(),
                TimeUnit.SECONDS
            )
            cache.set(userInfo)
            cachedUserInfo.put(username, cache)
        }
        return userInfo
    }

    @Throws(Exception::class)
    override fun createShare(ids: List<String>, description: String?, expires: Long?): List<Share> = musicService.createShare(ids, description, expires)

    @Throws(Exception::class)
    override fun deleteShare(id: String) {
        musicService.deleteShare(id)
    }

    @Throws(Exception::class)
    override fun updateShare(id: String, description: String?, expires: Long?) {
        musicService.updateShare(id, description, expires)
    }

    @Throws(Exception::class)
    override fun getMumaTiles(): List<MumaTile> = musicService.getMumaTiles()

    @Throws(Exception::class)
    override fun saveMumaTile(tile: MumaTile): String = musicService.saveMumaTile(tile)

    @Throws(Exception::class)
    override fun deleteMumaTile(id: String) {
        musicService.deleteMumaTile(id)
    }

    @Throws(Exception::class)
    override fun getMumaSettings(userId: Int, appId: String): String? = musicService.getMumaSettings(userId, appId)

    @Throws(Exception::class)
    override fun saveMumaSettings(userId: Int, appId: String, settings: String) {
        musicService.saveMumaSettings(userId, appId, settings)
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
        musicService.uploadCrashReport(
            deviceModel,
            osVersion,
            appVersionName,
            appVersionCode,
            buildType,
            ringBufferText,
            stacktraceText
        )
    }

    companion object {
        private const val MUSIC_DIR_CACHE_SIZE = 100
        private const val HOME_LIST_CACHE_SECONDS = 600L
        private const val ARTIST_CACHE_SECONDS = 3600L
        const val CACHE_KEY_VIDEOS = "VIDEOS"
    }

    init {
        cachedMusicDirectories = LRUCache(MUSIC_DIR_CACHE_SIZE)
        cachedAlbum = LRUCache(MUSIC_DIR_CACHE_SIZE)
        cachedUserInfo = LRUCache(MUSIC_DIR_CACHE_SIZE)
    }
}

/**
 * Whether [CachedMusicService.getArtists] has to skip its Room cache and go straight to
 * [musicService][CachedMusicService].
 *
 * The cache is [ArtistDao.get] - a plain `SELECT * FROM artists` with no `LIMIT`/`OFFSET`/
 * `ORDER BY`, and its result is never clamped to a requested [count]. It can only stand in for
 * a request that wants the *whole* library in whatever order the table happens to hold it, e.g.
 * [nl.teunschriks.mumamobile.fragment.muma.SelectFragment]'s `getArtists(refresh, null, null)`.
 * Any *paged* request - one that passes a [count] - needs the server to do the limiting,
 * ordering and offsetting, because the DAO has no way to answer any of that: serving it from
 * cache would return the entire table as "page 1" and then let the pager append rows it already
 * has. A search term or a non-default sort needs the server for the same reason.
 */
internal fun artistsCacheBypassesFor(query: String?, sortBy: String?, count: Int?): Boolean = query != null ||
    (sortBy != null && sortBy != "name") ||
    count != null

/**
 * Writes a rating into every cached copy of the track it belongs to.
 *
 * A rating used to be forwarded to the server and nowhere else, so the copies the app answers
 * from - the album it was rated in, the home screen lists, the car's browse tree - kept the
 * rating they were fetched with until their cache expired. Coming back to a track then showed the
 * old number, which reads as the rating having been reset.
 *
 * [cached] is walked rather than typed because the caches hold several shapes: a [MusicDirectory]
 * (itself a list of children), a home list of mixed entries, or a bare [Track].
 */
internal fun applyRatingToCachedTracks(cached: Any?, id: String, rating: Int) {
    when (cached) {
        is Track -> if (cached.id == id) cached.userRating = rating
        is Iterable<*> -> cached.forEach { applyRatingToCachedTracks(it, id, rating) }
    }
}
