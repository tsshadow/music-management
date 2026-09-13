package nl.teunschriks.mumamobile.capacitor

import androidx.room.Room
import java.util.Date
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.MetaDatabase
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.shouldBeEqualTo
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The contract `platform.storage.query` publishes to the web player.
 *
 * Every expectation here is a **hand-written** LMS body, read off the `subsonic-api` response and
 * model classes rather than captured from a run, because that is the only way the assertion can
 * catch the code drifting away from the server instead of drifting along with it. They are
 * compared as whole strings: field names, nesting, types and the server's own ids all have to
 * match, since an offline row and an online row of the same track must be interchangeable in one
 * list.
 *
 * The library is a real in-memory Room database with four tracks -- two under ten minutes, one
 * over, and one the device never downloaded -- because the boundary between the songs and the
 * sets mode and the boundary between "cached metadata" and "actually on the device" are the two
 * things this class exists to get right.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class OfflineSubsonicTest {

    private lateinit var database: MetaDatabase
    private lateinit var offline: OfflineSubsonic

    private var playlistRecords: List<OfflineSubsonic.PlaylistRecord> = emptyList()

    @Before
    fun setUp() {
        database = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), MetaDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        database.trackDao().set(listOf(shortOne, shortTwo, longSet, notDownloaded))
        playlistRecords = emptyList()
        offline = OfflineSubsonic(
            allTracks = { database.trackDao().get() },
            onDisk = { it.id in DOWNLOADED },
            coverArtUrl = { track -> if (track.coverArt == "art-tr-1") COVER_URL else null },
            playlists = { playlistRecords }
        )
    }

    @After
    fun tearDown() = database.close()

    private fun answer(method: String, vararg params: Pair<String, Any>): String {
        val json = JSONObject()
        params.forEach { (key, value) -> json.put(key, value) }
        return offline.answer(method, json).toString()
    }

    // ------------------------------------------------------------------ the shapes

    @Test
    fun `getSong answers the song node LMS answers with`() {
        answer("getSong", "id" to "tr-1") shouldBeEqualTo """{"subsonic-response":{$OK,"song":$TRACK_ONE}}"""
    }

    @Test
    fun `getGenres counts only what is on the device`() {
        answer("getGenres") shouldBeEqualTo
            """{"subsonic-response":{$OK,"genres":{"genre":[""" +
            """{"value":"Hardstyle","songCount":2,"albumCount":1},""" +
            """{"value":"Techno","songCount":1,"albumCount":1}]}}}"""
    }

    @Test
    fun `getYears answers the same node shape as getGenres`() {
        answer("getYears") shouldBeEqualTo
            """{"subsonic-response":{$OK,"years":{"year":[""" +
            """{"value":"2023","songCount":1,"albumCount":1},""" +
            """{"value":"2024","songCount":2,"albumCount":1}]}}}"""
    }

    @Test
    fun `getRecordLabels answers the labels the downloaded tracks carry`() {
        answer("getRecordLabels") shouldBeEqualTo
            """{"subsonic-response":{$OK,"recordLabels":{"recordLabel":[""" +
            """{"value":"Q-dance","songCount":1,"albumCount":1}]}}}"""
    }

    @Test
    fun `getSpotifyTracks answers the tracks node with its paging flags`() {
        answer("getSpotifyTracks", "maxDuration" to 10) shouldBeEqualTo
            """{"subsonic-response":{$OK,"tracks":{"moreResults":false,"nextOffset":2,""" +
            """"track":[$TRACK_ONE,$TRACK_TWO]}}}"""
    }

    @Test
    fun `getAlbumList2 answers albums derived from the downloaded tracks`() {
        answer("getAlbumList2", "type" to "alphabeticalByName", "size" to 10) shouldBeEqualTo
            """{"subsonic-response":{$OK,"albumList2":{"album":[$ALBUM_ONE,$ALBUM_TWO]}}}"""
    }

    @Test
    fun `getAlbum answers the album with its downloaded songs`() {
        answer("getAlbum", "id" to "al-1") shouldBeEqualTo
            """{"subsonic-response":{$OK,"album":${ALBUM_ONE.dropLast(1)},"song":[$TRACK_ONE,$TRACK_TWO]}}}"""
    }

    @Test
    fun `getArtistList answers a flat artist array`() {
        answer("getArtistList", "type" to "alphabetical") shouldBeEqualTo
            """{"subsonic-response":{$OK,"artistList":{"artist":[$ARTIST_ONE,$ARTIST_TWO]}}}"""
    }

    @Test
    fun `getArtist answers the artist with the albums it has on the device`() {
        answer("getArtist", "id" to "ar-1") shouldBeEqualTo
            """{"subsonic-response":{$OK,"artist":${ARTIST_ONE.dropLast(1)},"album":[$ALBUM_ONE]}}}"""
    }

    @Test
    fun `search3 answers all three sections of searchResult3`() {
        answer("search3", "query" to "long") shouldBeEqualTo
            """{"subsonic-response":{$OK,"searchResult3":{"artist":[$ARTIST_TWO],""" +
            """"album":[$ALBUM_TWO],"song":[$LONG_SET]}}}"""
    }

    @Test
    fun `getStarred2 answers only the favourites that are on the device`() {
        answer("getStarred2") shouldBeEqualTo
            """{"subsonic-response":{$OK,"starred2":{"artist":[$STARRED_ARTIST],""" +
            """"album":[$STARRED_ALBUM],"song":[$TRACK_ONE]}}}"""
    }

    // ------------------------------------------------------------------- playlists

    @Test
    fun `getPlaylists answers every remembered playlist, its downloaded songs only`() {
        playlistRecords = listOf(
            OfflineSubsonic.PlaylistRecord(id = "pl-1", name = "Warm-up", trackIds = listOf("tr-1", "tr-4", "tr-2"))
        )
        answer("getPlaylists") shouldBeEqualTo
            """{"subsonic-response":{$OK,"playlists":{"playlist":[""" +
            """{"id":"pl-1","name":"Warm-up","songCount":2,"duration":800,"coverArt":"art-tr-1"}]}}}"""
    }

    @Test
    fun `getPlaylist answers the playlist with its entries in playlist order`() {
        playlistRecords = listOf(
            OfflineSubsonic.PlaylistRecord(id = "pl-1", name = "Warm-up", trackIds = listOf("tr-2", "tr-1"))
        )
        answer("getPlaylist", "id" to "pl-1") shouldBeEqualTo
            """{"subsonic-response":{$OK,"playlist":{"id":"pl-1","name":"Warm-up","songCount":2,""" +
            """"duration":800,"coverArt":"art-tr-2","entry":[$TRACK_TWO,$TRACK_ONE]}}}"""
    }

    @Test
    fun `a track a playlist remembers but the device never downloaded is left out`() {
        playlistRecords = listOf(OfflineSubsonic.PlaylistRecord(id = "pl-1", name = "Warm-up", trackIds = listOf("tr-4")))
        answer("getPlaylist", "id" to "pl-1") shouldBeEqualTo
            """{"subsonic-response":{$OK,"playlist":{"id":"pl-1","name":"Warm-up","songCount":0,"duration":0,"entry":[]}}}"""
    }

    @Test
    fun `a playlist id nobody remembers is not found rather than empty`() {
        answer("getPlaylist", "id" to "does-not-exist") shouldBeEqualTo
            """{"subsonic-response":{"status":"failed","version":"1.16.1","type":"lms","openSubsonic":true,""" +
            """"error":{"code":70,"message":"The requested data was not found."}}}"""
    }

    /** `.view` and a leading path are both things the web sends; neither is a different request. */
    @Test
    fun `a method name survives its suffix and its path`() {
        answer("/rest/getGenres.view") shouldBeEqualTo answer("getGenres")
    }

    // --------------------------------------------------------------- what is in it

    @Test
    fun `a track whose file is not on the device is never listed`() {
        val ids = idsOf(answer("getSpotifyTracks", "count" to 50))
        ids shouldBeEqualTo listOf("tr-3", "tr-1", "tr-2")
    }

    @Test
    fun `an album only its undownloaded track belongs to is not offered`() {
        answer("getAlbum", "id" to "al-3") shouldBeEqualTo
            """{"subsonic-response":{"status":"failed","version":"1.16.1","type":"lms","openSubsonic":true,""" +
            """"error":{"code":70,"message":"The requested data was not found."}}}"""
    }

    // ------------------------------------------------------------- duration filters

    @Test
    fun `maxDuration is minutes and keeps the songs side of the boundary`() {
        idsOf(answer("getSpotifyTracks", "maxDuration" to 10)) shouldBeEqualTo listOf("tr-1", "tr-2")
    }

    @Test
    fun `minDuration is minutes and keeps the sets side of the boundary`() {
        idsOf(answer("getSpotifyTracks", "minDuration" to 10)) shouldBeEqualTo listOf("tr-3", "tr-2")
    }

    /** Ten minutes exactly is on both sides, because both bounds are inclusive on the server. */
    @Test
    fun `a recording of exactly ten minutes is a song and a set`() {
        idsOf(answer("getSpotifyTracks", "minDuration" to 10, "maxDuration" to 10)) shouldBeEqualTo listOf("tr-2")
    }

    @Test
    fun `search3 honours the duration bounds the search bar sends`() {
        val body = JSONObject(answer("search3", "query" to "", "minDuration" to 10))
        val songs = body.getJSONObject(OfflineSubsonic.RESPONSE).getJSONObject("searchResult3").getJSONArray("song")
        (0 until songs.length()).map { songs.getJSONObject(it).getString("id") } shouldBeEqualTo listOf("tr-2", "tr-3")
    }

    // ------------------------------------------------------- filters, paging, sorting

    @Test
    fun `genre filters the track list`() {
        idsOf(answer("getSpotifyTracks", "genre" to "techno")) shouldBeEqualTo listOf("tr-3")
    }

    @Test
    fun `genre filters an album list whatever its type is`() {
        val body = JSONObject(answer("getAlbumList2", "type" to "newest", "genre" to "Techno"))
        val albums = body.getJSONObject(OfflineSubsonic.RESPONSE).getJSONObject("albumList2").getJSONArray("album")
        albums.length() shouldBeEqualTo 1
        albums.getJSONObject(0).getString("id") shouldBeEqualTo "al-2"
    }

    @Test
    fun `size and offset page an album list`() {
        val body = JSONObject(answer("getAlbumList2", "type" to "alphabeticalByName", "size" to 1, "offset" to 1))
        val albums = body.getJSONObject(OfflineSubsonic.RESPONSE).getJSONObject("albumList2").getJSONArray("album")
        albums.length() shouldBeEqualTo 1
        albums.getJSONObject(0).getString("id") shouldBeEqualTo "al-2"
    }

    @Test
    fun `offset and count page the track list and report where to continue`() {
        val body = JSONObject(answer("getSpotifyTracks", "count" to 2, "offset" to 0))
            .getJSONObject(OfflineSubsonic.RESPONSE)
            .getJSONObject("tracks")
        body.getBoolean("moreResults") shouldBeEqualTo true
        body.getInt("nextOffset") shouldBeEqualTo 2
    }

    @Test
    fun `the default track sort is what was added last`() {
        idsOf(answer("getSpotifyTracks")) shouldBeEqualTo listOf("tr-3", "tr-1", "tr-2")
    }

    @Test
    fun `alphabetical sorts the track list by title`() {
        idsOf(answer("getSpotifyTracks", "sort" to "alpha")) shouldBeEqualTo listOf("tr-2", "tr-1", "tr-3")
    }

    @Test
    fun `random is stable for one seed and the whole library is still there`() {
        val once = idsOf(answer("getSpotifyTracks", "sort" to "random", "seed" to 7))
        val twice = idsOf(answer("getSpotifyTracks", "sort" to "random", "seed" to 7))
        once shouldBeEqualTo twice
        once.sorted() shouldBeEqualTo listOf("tr-1", "tr-2", "tr-3")
    }

    @Test
    fun `a rating floor keeps unrated tracks unless the caller says otherwise`() {
        idsOf(answer("getSpotifyTracks", "minRating" to 5)) shouldBeEqualTo listOf("tr-3", "tr-1", "tr-2")
        idsOf(answer("getSpotifyTracks", "minRating" to 5, "includeUnrated" to false)) shouldBeEqualTo listOf("tr-1")
    }

    @Test
    fun `a search query matches title, artist and album`() {
        idsOf(answer("getSpotifyTracks", "query" to "album two")) shouldBeEqualTo listOf("tr-3")
    }

    // ------------------------------------------------------------------- cover art

    /** `org.json` escapes every slash in a string; `JSON.parse` on the other side undoes it. */
    @Test
    fun `getCoverArt answers a URL the WebView can load`() {
        answer("getCoverArt", "id" to "art-tr-1") shouldBeEqualTo
            """{"subsonic-response":{$OK,"url":"https:\/\/localhost\/_capacitor_file_\/data\/artwork\/abc"}}"""
        JSONObject(answer("getCoverArt", "id" to "art-tr-1"))
            .getJSONObject(OfflineSubsonic.RESPONSE)
            .getString("url") shouldBeEqualTo COVER_URL
    }

    @Test
    fun `a cover this device never cached is refused rather than faked`() {
        answer("getCoverArt", "id" to "art-tr-2") shouldBeEqualTo
            """{"subsonic-response":{"status":"failed","version":"1.16.1","type":"lms","openSubsonic":true,""" +
            """"error":{"code":70,"message":"The requested data was not found."}}}"""
    }

    // ----------------------------------------------------------------- unsupported

    @Test
    fun `an unsupported method answers an empty success body rather than an error`() {
        answer("getMemories", "date" to "2026-09-12") shouldBeEqualTo """{"subsonic-response":{$OK}}"""
        answer("getSpotifyHistory") shouldBeEqualTo """{"subsonic-response":{$OK}}"""
        answer("stream", "id" to "tr-1") shouldBeEqualTo """{"subsonic-response":{$OK}}"""
    }

    @Test
    fun `ping succeeds offline, because the local library is there`() {
        answer("ping") shouldBeEqualTo """{"subsonic-response":{$OK}}"""
    }

    // ---------------------------------------------------------------------- helpers

    private fun idsOf(body: String): List<String> {
        val tracks = JSONObject(body).getJSONObject(OfflineSubsonic.RESPONSE).getJSONObject("tracks").getJSONArray("track")
        return (0 until tracks.length()).map { tracks.getJSONObject(it).getString("id") }
    }

    private companion object {
        /** 2023-11-14T22:13:20Z, so every timestamp below is readable rather than "now". */
        const val BASE_MS = 1_700_000_000_000L
        const val COVER_URL = "https://localhost/_capacitor_file_/data/artwork/abc"

        val DOWNLOADED = setOf("tr-1", "tr-2", "tr-3")

        val shortOne = track(
            id = "tr-1",
            title = "Short One",
            albumId = "al-1",
            album = "Album One",
            artistId = "ar-1",
            artist = "Artist One",
            duration = 200,
            genre = "Hardstyle",
            year = 2024,
            createdMs = BASE_MS + 3_000,
            rating = 5,
            favourite = true
        )

        val shortTwo = track(
            id = "tr-2",
            title = "Second Short",
            albumId = "al-1",
            album = "Album One",
            artistId = "ar-1",
            artist = "Artist One",
            duration = 600,
            genre = "Hardstyle",
            year = 2024,
            createdMs = BASE_MS + 2_000,
            labels = listOf("Q-dance")
        )

        val longSet = track(
            id = "tr-3",
            title = "The Long Set",
            albumId = "al-2",
            album = "Album Two",
            artistId = "ar-2",
            artist = "Artist Two",
            duration = 3_600,
            genre = "Techno",
            year = 2023,
            createdMs = BASE_MS + 4_000
        )

        val notDownloaded = track(
            id = "tr-4",
            title = "Never Fetched",
            albumId = "al-3",
            album = "Album Three",
            artistId = "ar-3",
            artist = "Artist Three",
            duration = 180,
            genre = "Hardstyle",
            year = 2024,
            createdMs = BASE_MS
        )

        @Suppress("LongParameterList")
        fun track(
            id: String,
            title: String,
            albumId: String,
            album: String,
            artistId: String,
            artist: String,
            duration: Int,
            genre: String,
            year: Int,
            createdMs: Long,
            rating: Int? = null,
            favourite: Boolean = false,
            labels: List<String> = emptyList()
        ) = Track(
            id = id,
            serverId = 1,
            title = title,
            album = album,
            albumId = albumId,
            artist = artist,
            artistId = artistId,
            year = year,
            genre = genre,
            genres = listOf(genre),
            date = "$year-03-01",
            coverArt = "art-$id",
            duration = duration,
            starred = favourite,
            created = Date(createdMs),
            userRating = rating,
            labels = labels
        )

        // -------------------------------------------------------------- the goldens

        const val OK = """"status":"ok","version":"1.16.1","type":"lms","openSubsonic":true"""

        const val TRACK_ONE = """{"id":"tr-1","isDir":false,"mediaType":"song","type":"music","isCanonical":true,""" +
            """"title":"Short One","album":"Album One","albumId":"al-1","artist":"Artist One",""" +
            """"displayArtist":"Artist One","artistId":"ar-1","year":2024,"date":"2024-03-01",""" +
            """"originalDate":"2024-03-01","coverArt":"art-tr-1","duration":200,"userRating":5,""" +
            """"created":"2023-11-14T22:13:23.000Z","starred":"2023-11-14T22:13:23.000Z","genre":"Hardstyle",""" +
            """"genres":[{"name":"Hardstyle"}],"artists":[],"moods":[],"labels":[]}"""

        const val TRACK_TWO = """{"id":"tr-2","isDir":false,"mediaType":"song","type":"music","isCanonical":true,""" +
            """"title":"Second Short","album":"Album One","albumId":"al-1","artist":"Artist One",""" +
            """"displayArtist":"Artist One","artistId":"ar-1","year":2024,"date":"2024-03-01",""" +
            """"originalDate":"2024-03-01","coverArt":"art-tr-2","duration":600,""" +
            """"created":"2023-11-14T22:13:22.000Z","genre":"Hardstyle",""" +
            """"genres":[{"name":"Hardstyle"}],"artists":[],"moods":[],"labels":["Q-dance"]}"""

        const val LONG_SET = """{"id":"tr-3","isDir":false,"mediaType":"song","type":"music","isCanonical":true,""" +
            """"title":"The Long Set","album":"Album Two","albumId":"al-2","artist":"Artist Two",""" +
            """"displayArtist":"Artist Two","artistId":"ar-2","year":2023,"date":"2023-03-01",""" +
            """"originalDate":"2023-03-01","coverArt":"art-tr-3","duration":3600,""" +
            """"created":"2023-11-14T22:13:24.000Z","genre":"Techno",""" +
            """"genres":[{"name":"Techno"}],"artists":[],"moods":[],"labels":[]}"""

        const val ALBUM_ONE = """{"id":"al-1","name":"Album One","mediaType":"album","songCount":2,"duration":800,""" +
            """"artist":"Artist One","displayArtist":"Artist One","artistId":"ar-1","coverArt":"art-tr-1",""" +
            """"year":2024,"created":"2023-11-14T22:13:23.000Z","genre":"Hardstyle",""" +
            """"starred":"2023-11-14T22:13:23.000Z","genres":[{"name":"Hardstyle"}]}"""

        const val ALBUM_TWO = """{"id":"al-2","name":"Album Two","mediaType":"album","songCount":1,"duration":3600,""" +
            """"artist":"Artist Two","displayArtist":"Artist Two","artistId":"ar-2","coverArt":"art-tr-3",""" +
            """"year":2023,"created":"2023-11-14T22:13:24.000Z","genre":"Techno",""" +
            """"genres":[{"name":"Techno"}]}"""

        const val STARRED_ALBUM = """{"id":"al-1","name":"Album One","mediaType":"album","songCount":1,"duration":200,""" +
            """"artist":"Artist One","displayArtist":"Artist One","artistId":"ar-1","coverArt":"art-tr-1",""" +
            """"year":2024,"created":"2023-11-14T22:13:23.000Z","genre":"Hardstyle",""" +
            """"starred":"2023-11-14T22:13:23.000Z","genres":[{"name":"Hardstyle"}]}"""

        const val ARTIST_ONE = """{"id":"ar-1","name":"Artist One","mediaType":"artist","albumCount":1,""" +
            """"songCount":2,"coverArt":"art-tr-1","starred":"2023-11-14T22:13:23.000Z"}"""

        const val ARTIST_TWO = """{"id":"ar-2","name":"Artist Two","mediaType":"artist","albumCount":1,""" +
            """"songCount":1,"coverArt":"art-tr-3"}"""

        const val STARRED_ARTIST = """{"id":"ar-1","name":"Artist One","mediaType":"artist","albumCount":1,""" +
            """"songCount":1,"coverArt":"art-tr-1","starred":"2023-11-14T22:13:23.000Z"}"""
    }
}
