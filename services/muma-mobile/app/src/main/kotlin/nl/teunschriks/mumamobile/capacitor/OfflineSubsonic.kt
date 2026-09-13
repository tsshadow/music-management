/*
 * OfflineSubsonic.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import java.text.SimpleDateFormat
import java.util.Collections
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.max
import kotlin.random.Random
import nl.teunschriks.mumamobile.domain.Track
import org.json.JSONArray
import org.json.JSONObject
import timber.log.Timber

/**
 * The downloaded library, answered in the shape LMS answers in.
 *
 * This is what `platform.storage.query({method, params})` resolves to. The web player must not
 * learn a second data source: a list component sends the same `/rest` method name with the same
 * query parameters it would send to the server, reads the same `{"subsonic-response": {...}}`
 * body out of the answer, and gets rows carrying **the server's own ids** -- so an offline row
 * and an online row of the same track are the same row, and the two can be mixed in one list.
 *
 * ### What is in it
 *
 * Only tracks whose file is on this device ([onDisk] -- the `done` state of
 * `platform.storage.stateOf`). Albums, artists, genres, years and labels are *derived from those
 * tracks*: an album appears exactly when one of its tracks is downloaded, and its `songCount`
 * counts the downloaded ones. The Room caches for albums and artists are deliberately not read:
 * browsing a library caches thousands of rows that are not on the device, and listing those
 * offline would offer music that cannot play.
 *
 * ### What it is not
 *
 * Not byte-identical to LMS. The field names, the nesting and the ids are; the envelope's
 * `serverVersion` is absent (this device does not know it), key order is insertion order rather
 * than LMS's lexicographic sort -- the body crosses the bridge as a JavaScript object, where key
 * order is not part of the contract -- and the fields [songNode] documents as missing are omitted
 * rather than guessed.
 *
 * A method this class does not implement answers the **empty success body**, never an error: an
 * offline list that renders empty is a UI state, an offline list that throws is a bug report.
 * Each such method is logged once, so the log says which one the web reached for rather than
 * repeating it per scroll.
 *
 * @param allTracks every track the per-server Room cache holds. Called on a background thread.
 * @param onDisk whether that track's file is actually on the device.
 * @param coverArtUrl an absolute URL the WebView can load the track's artwork from, or null when
 *   this device cannot serve it cheaply. See [MumaStoragePlugin.query].
 * @param playlists every playlist this device remembers, merged from the `offline_playlists`
 *   Room table and any `.m3u` file downloaded before that table existed. See [PlaylistRecord].
 */
@Suppress("TooManyFunctions")
class OfflineSubsonic(
    private val allTracks: () -> List<Track>,
    private val onDisk: (Track) -> Boolean,
    private val coverArtUrl: (Track) -> String? = { null },
    private val playlists: () -> List<PlaylistRecord> = { emptyList() }
) {

    /**
     * One playlist, the way this device remembers it: a server id, a name and the ids of the
     * tracks it held the last time the app fetched it -- in playlist order.
     *
     * A track that is not [onDisk] is silently dropped when this is answered, the same way an
     * undownloaded track never appears in any other list here; a playlist is not a promise that
     * every one of these ids still resolves to a played file.
     *
     * @param id the server's playlist id, or a synthetic one for a `.m3u` file downloaded before
     *   this device started remembering it (see `LegacyPlaylistFiles`). Stable across calls
     *   either way, which is what lets the web treat this row as one playlist rather than a new
     *   one every time the list is drawn.
     */
    data class PlaylistRecord(val id: String, val name: String, val trackIds: List<String>)

    /**
     * The downloaded set, held between calls because one screen makes several: a list, its filter
     * chips and the download glyphs are three methods over the same files. Dropped by
     * [invalidate] whenever a download finishes or is removed, which is the only thing that can
     * change it.
     */
    @Volatile
    private var memo: List<Track>? = null

    private val logged: MutableSet<String> = Collections.newSetFromMap(ConcurrentHashMap())

    /** Called by [MumaStoragePlugin] on every download state change. */
    fun invalidate() {
        memo = null
    }

    /**
     * The whole `{"subsonic-response": {...}}` body for one request.
     *
     * @param method a `/rest` method name, with or without the `.view` suffix and with or without
     *   a leading path: `getGenres`, `getGenres.view` and `/rest/getGenres.view` are one request,
     *   because the callers on the web side are not consistent about it.
     * @param params the query parameters, as the web would have put them in the URL.
     */
    fun answer(method: String, params: JSONObject): JSONObject = JSONObject().put(RESPONSE, body(normalise(method), params))

    private fun normalise(method: String): String = method.trim().trimStart('/').substringAfterLast('/').removeSuffix(".view")

    private fun body(method: String, params: JSONObject): JSONObject = when (method) {
        "ping" -> ok()
        "getGenres" -> ok().put("genres", JSONObject().put("genre", valueCounts { it.genreNames() }))
        "getYears" -> ok().put("years", JSONObject().put("year", valueCounts { listOfNotNull(it.year?.toString()) }))
        "getRecordLabels" -> ok().put("recordLabels", JSONObject().put("recordLabel", valueCounts { it.labels }))
        "getSpotifyTracks" -> tracks(params)
        "getAlbumList2" -> ok().put("albumList2", JSONObject().put("album", albumList(params)))
        "getAlbum" -> album(params)
        "getArtistList" -> ok().put("artistList", JSONObject().put("artist", artistList(params)))
        "getArtist" -> artist(params)
        "search3" -> ok().put("searchResult3", searchResult(params))
        "getStarred2" -> ok().put("starred2", starred())
        "getSong" -> song(params)
        "getCoverArt" -> coverArt(params)
        "getPlaylists" -> ok().put("playlists", JSONObject().put("playlist", playlistArray()))
        "getPlaylist" -> playlist(params)
        else -> unsupported(method)
    }

    private fun unsupported(method: String): JSONObject {
        if (logged.add(method)) {
            Timber.i("No offline answer for /rest/%s; the web UI gets an empty result", method)
        }
        return ok()
    }

    private fun downloaded(): List<Track> {
        memo?.let { return it }
        val fresh = allTracks().filter(onDisk)
        memo = fresh
        return fresh
    }

    // ------------------------------------------------------------------ getSpotifyTracks

    /**
     * The web player's main track list, and the one the songs/sets toggle drives.
     *
     * `minDuration`/`maxDuration` are **minutes**, as LMS reads them on this endpoint and on
     * `search3` -- not the seconds the Kotlin `MusicService` uses. `maxDuration=10` is the songs
     * side of the ten-minute boundary and `minDuration=10` is the sets side; a recording of
     * exactly ten minutes is on both, exactly as the server has it.
     */
    private fun tracks(params: JSONObject): JSONObject {
        val matching = sorted(filtered(downloaded(), params), params.text("sort"), params.number("seed"))
        val offset = max(0, params.number("offset") ?: 0)
        val count = params.number("count") ?: DEFAULT_TRACK_COUNT
        val page = matching.drop(offset).take(count)
        val node = JSONObject()
            .put("moreResults", offset + page.size < matching.size)
            .put("nextOffset", offset + page.size)
            .put("track", page.jsonArray(::songNode))
        return ok().put("tracks", node)
    }

    private fun filtered(source: List<Track>, params: JSONObject): List<Track> {
        var list = source
        params.text("genre")?.let { wanted -> list = list.filter { t -> t.genreNames().any { it.equals(wanted, true) } } }
        params.text("label")?.let { wanted -> list = list.filter { t -> t.labels.any { it.equals(wanted, true) } } }
        params.number("year")?.let { wanted -> list = list.filter { it.year == wanted } }
        params.text("artistId")?.let { id -> list = list.filter { t -> t.artistId == id || t.artists.any { it.id == id } } }
        params.text("artist")?.let { name -> list = list.filter { it.artist.equals(name, true) } }
        params.text("albumId")?.let { id -> list = list.filter { it.albumId == id } }
        params.number("workId")?.let { id -> list = list.filter { it.workId == id } }
        params.number("minDuration")?.let { min -> list = list.filter { (it.duration ?: 0) >= min * SECONDS_PER_MINUTE } }
        params.number("maxDuration")?.let { top -> list = list.filter { (it.duration ?: 0) <= top * SECONDS_PER_MINUTE } }
        list = byRating(list, params)
        params.text("query")?.let { query -> list = list.filter { matches(it, query) } }
        if (params.flag("canonicalOnly") == true) list = list.filter { it.isCanonical }
        return list
    }

    /** `includeUnrated` defaults to true, as it does on the server; without it a floor hides everything unrated. */
    private fun byRating(source: List<Track>, params: JSONObject): List<Track> {
        var list = source
        params.number("minRating")?.takeIf { it > 0 }?.let { min ->
            val includeUnrated = params.flag("includeUnrated") ?: true
            list = list.filter { track ->
                val rating = track.userRating ?: 0
                if (rating == 0) includeUnrated else rating >= min
            }
        }
        params.number("maxRating")?.let { top -> list = list.filter { (it.userRating ?: 0) <= top } }
        return list
    }

    /**
     * `mostplayed` and `recentlyplayed` have no offline answer -- play counts live on the server --
     * so they fall back to what was added last rather than refusing the request.
     */
    private fun sorted(list: List<Track>, sort: String?, seed: Int?): List<Track> = when (sort?.lowercase(Locale.ROOT)) {
        "random" -> list.shuffled(Random(seed ?: 0))
        "alpha", "alphabetical" -> list.sortedBy { it.title?.lowercase(Locale.ROOT).orEmpty() }
        "releasedate" -> list.sortedWith(compareByDescending<Track> { it.date.orEmpty() }.thenByDescending { it.year ?: 0 })
        "rating" -> list.sortedByDescending { it.userRating ?: 0 }
        "starred" -> list.sortedWith(compareByDescending<Track> { it.starred }.thenByDescending { it.created?.time ?: 0L })
        else -> list.sortedByDescending { it.created?.time ?: 0L }
    }

    // ---------------------------------------------------------------------- album lists

    /**
     * One album per `albumId` that at least one downloaded track belongs to.
     *
     * `genre` filters whatever the `type` is. LMS only requires it for `type=byGenre`, but the web
     * appends it to every album request the collection bar makes and expects it to bite.
     */
    private fun albumList(params: JSONObject): JSONArray {
        var albums = albums(downloaded())
        params.text("genre")?.let { wanted -> albums = albums.filter { album -> album.genres.any { it.equals(wanted, true) } } }
        params.number("fromYear")?.let { from -> albums = albums.filter { (it.year ?: 0) >= from } }
        params.number("toYear")?.let { to -> albums = albums.filter { (it.year ?: 0) <= to } }
        params.text("query")?.let { query -> albums = albums.filter { matchesAll(query, it.name, it.artist) } }
        val offset = max(0, params.number("offset") ?: 0)
        val size = params.number("size") ?: DEFAULT_ALBUM_SIZE
        return orderAlbums(albums, params.text("type"))
            .drop(offset)
            .take(size)
            .jsonArray { albumNode(it, withSongs = false) }
    }

    private fun orderAlbums(albums: List<OfflineAlbum>, type: String?): List<OfflineAlbum> = when (type?.lowercase(Locale.ROOT)) {
        "alphabeticalbyname", "alphabetical" -> albums.sortedBy { it.name.lowercase(Locale.ROOT) }
        "alphabeticalbyartist", "byartist" -> albums.sortedBy { it.artist.orEmpty().lowercase(Locale.ROOT) }
        "random" -> albums.shuffled()
        "starred" -> albums.filter { it.starred }.sortedByDescending { it.created?.time ?: 0L }
        "bytrackcount" -> albums.sortedByDescending { it.tracks.size }
        "byyear", "year" -> albums.sortedByDescending { it.year ?: 0 }
        else -> albums.sortedByDescending { it.created?.time ?: 0L }
    }

    private fun album(params: JSONObject): JSONObject {
        val id = params.text("id") ?: return notFound()
        val found = albums(downloaded()).firstOrNull { it.id == id } ?: return notFound()
        return ok().put("album", albumNode(found, withSongs = true))
    }

    // --------------------------------------------------------------------- artist lists

    private fun artistList(params: JSONObject): JSONArray {
        var list = artists(downloaded())
        params.text("query")?.let { query -> list = list.filter { matchesAll(query, it.name) } }
        list = when (params.text("type")?.lowercase(Locale.ROOT)) {
            "trackcount" -> list.sortedByDescending { it.tracks.size }
            "random" -> list.shuffled()
            "newest", "recent", "updated" -> list.sortedByDescending { it.created?.time ?: 0L }
            "starred" -> list.filter { it.starred }.sortedBy { it.name.lowercase(Locale.ROOT) }
            else -> list.sortedBy { it.name.lowercase(Locale.ROOT) }
        }
        val offset = max(0, params.number("offset") ?: 0)
        val size = params.number("size") ?: params.number("count") ?: DEFAULT_ARTIST_SIZE
        return list.drop(offset).take(size).jsonArray { artistNode(it, withAlbums = false) }
    }

    private fun artist(params: JSONObject): JSONObject {
        val id = params.text("id") ?: return notFound()
        val found = artists(downloaded()).firstOrNull { it.id == id } ?: return notFound()
        return ok().put("artist", artistNode(found, withAlbums = true))
    }

    // ----------------------------------------------------------------- search & starred

    private fun searchResult(params: JSONObject): JSONObject {
        val query = params.text("query").orEmpty()
        val hits = downloaded().filter { matches(it, query) }
        return JSONObject()
            .put("artist", page(artists(hits), params, "artistCount") { artistNode(it, withAlbums = false) })
            .put("album", page(albums(hits), params, "albumCount") { albumNode(it, withSongs = false) })
            .put("song", page(filtered(hits, durationOnly(params)), params, "songCount", ::songNode))
    }

    /** `search3` reads the duration bounds; the other filters [filtered] knows are not its parameters. */
    private fun durationOnly(params: JSONObject): JSONObject {
        val copy = JSONObject()
        params.text("minDuration")?.let { copy.put("minDuration", it) }
        params.text("maxDuration")?.let { copy.put("maxDuration", it) }
        return copy
    }

    private fun <T> page(items: List<T>, params: JSONObject, countKey: String, node: (T) -> JSONObject): JSONArray {
        val count = params.number(countKey) ?: DEFAULT_SEARCH_COUNT
        val offset = max(0, params.number(countKey.removeSuffix("Count") + "Offset") ?: 0)
        return items.drop(offset).take(count).jsonArray(node)
    }

    private fun starred(): JSONObject {
        val favourites = downloaded().filter { it.starred }
        return JSONObject()
            .put("artist", artists(favourites).jsonArray { artistNode(it, withAlbums = false) })
            .put("album", albums(favourites).jsonArray { albumNode(it, withSongs = false) })
            .put("song", favourites.jsonArray(::songNode))
    }

    private fun song(params: JSONObject): JSONObject {
        val id = params.text("id") ?: return notFound()
        val track = downloaded().firstOrNull { it.id == id } ?: return notFound()
        return ok().put("song", songNode(track))
    }

    /**
     * The one supported method whose answer is not JSON on the server.
     *
     * Answered with a `url` the WebView can load directly, so a Downloads tab draws its covers
     * without a bridge hop per row. Nothing is decoded or copied here: the app already keeps the
     * artwork it has fetched as a file, and [coverArtUrl] only turns an existing one into an
     * address. A cover this device never cached is a refusal (`70`) rather than a blank image --
     * the web falls back to its own placeholder when a request fails.
     */
    private fun coverArt(params: JSONObject): JSONObject {
        val id = params.text("id") ?: return notFound()
        val track = downloaded().firstOrNull { it.coverArt == id || it.id == id } ?: return notFound()
        val url = coverArtUrl(track) ?: return notFound()
        return ok().put("url", url)
    }

    // ------------------------------------------------------------------------- playlists

    private fun playlistArray(): JSONArray = playlists().jsonArray { playlistNode(it, withEntries = false) }

    private fun playlist(params: JSONObject): JSONObject {
        val id = params.text("id") ?: return notFound()
        val found = playlists().firstOrNull { it.id == id } ?: return notFound()
        return ok().put("playlist", playlistNode(found, withEntries = true))
    }

    /**
     * A playlist as [PlaylistRecord] and the downloaded set together describe it: its own id and
     * name, and whichever of its tracks are actually [onDisk] -- the rest are the same "not on
     * this device" gap every other list here leaves rather than papering over.
     */
    private fun playlistNode(record: PlaylistRecord, withEntries: Boolean): JSONObject {
        val matched = record.trackIds.mapNotNull { id -> downloaded().firstOrNull { it.id == id } }
        val node = JSONObject()
            .put("id", record.id)
            .put("name", record.name)
            .put("songCount", matched.size)
            .put("duration", matched.sumOf { it.duration ?: 0 })
        matched.firstNotNullOfOrNull { it.coverArt }?.let { node.put("coverArt", it) }
        if (withEntries) node.put("entry", matched.jsonArray(::songNode))
        return node
    }

    // -------------------------------------------------------------------- derived groups

    /** An album as the downloaded tracks describe it, with nothing filled in that the device lacks. */
    data class OfflineAlbum(
        val id: String,
        val name: String,
        val artist: String?,
        val artistId: String?,
        val coverArt: String?,
        val year: Int?,
        val created: Date?,
        val genres: List<String>,
        val starred: Boolean,
        val tracks: List<Track>
    )

    /** An artist as the downloaded tracks describe it. */
    data class OfflineArtist(
        val id: String,
        val name: String,
        val coverArt: String?,
        val created: Date?,
        val starred: Boolean,
        val tracks: List<Track>
    )

    private fun albums(tracks: List<Track>): List<OfflineAlbum> = tracks
        .filter { !it.albumId.isNullOrBlank() }
        .groupBy { it.albumId!! }
        .map { (id, members) -> offlineAlbum(id, members) }

    private fun offlineAlbum(id: String, members: List<Track>): OfflineAlbum = OfflineAlbum(
        id = id,
        name = members.firstNotNullOfOrNull { it.album } ?: members.first().title.orEmpty(),
        artist = members.firstNotNullOfOrNull { it.artist },
        artistId = members.firstNotNullOfOrNull { it.artistId },
        coverArt = members.firstNotNullOfOrNull { it.coverArt },
        year = members.firstNotNullOfOrNull { it.year },
        created = members.mapNotNull { it.created }.maxByOrNull { it.time },
        genres = members.flatMap { it.genreNames() }.distinct(),
        starred = members.any { it.starred },
        tracks = members.sortedWith(compareBy({ it.discNumber ?: 0 }, { it.track ?: 0 }))
    )

    private fun artists(tracks: List<Track>): List<OfflineArtist> {
        val byId = linkedMapOf<String, MutableList<Track>>()
        val names = mutableMapOf<String, String>()
        tracks.forEach { track ->
            artistRefsOf(track).forEach { (id, name) ->
                byId.getOrPut(id) { mutableListOf() }.add(track)
                if (name.isNotBlank()) names.putIfAbsent(id, name)
            }
        }
        return byId.map { (id, members) ->
            OfflineArtist(
                id = id,
                name = names[id] ?: id,
                coverArt = members.firstNotNullOfOrNull { it.coverArt },
                created = members.mapNotNull { it.created }.maxByOrNull { it.time },
                starred = members.any { it.starred },
                tracks = members
            )
        }
    }

    /** Every artist the track is credited to: the split list when the server sent one, else the tag. */
    private fun artistRefsOf(track: Track): List<Pair<String, String>> {
        val split = track.artists.filter { it.id.isNotBlank() }.map { it.id to it.name }
        if (split.isNotEmpty()) return split
        val id = track.artistId
        return if (id.isNullOrBlank()) emptyList() else listOf(id to track.artist.orEmpty())
    }

    /** The `{value, songCount, albumCount}` node getGenres, getYears and getRecordLabels share. */
    private fun valueCounts(values: (Track) -> List<String>): JSONArray {
        val byValue = linkedMapOf<String, MutableList<Track>>()
        downloaded().forEach { track ->
            values(track).filter { it.isNotBlank() }.distinct().forEach { value ->
                byValue.getOrPut(value) { mutableListOf() }.add(track)
            }
        }
        return byValue.entries
            .sortedBy { it.key.lowercase(Locale.ROOT) }
            .jsonArray { (value, members) ->
                JSONObject()
                    .put("value", value)
                    .put("songCount", members.size)
                    .put("albumCount", members.mapNotNull { it.albumId }.distinct().size)
            }
    }

    // ---------------------------------------------------------------------------- nodes

    /**
     * One track, under the keys LMS uses for a song.
     *
     * What is missing is what Room never cached: `playCount`, `globalPlayCount`, `bitDepth`,
     * `samplingRate`, `channelCount`, `musicBrainzId`, `comment`, `replayGain`, `versionScore`
     * and the contributor list. `starred` is a timestamp on the server and a flag here, so the
     * track's `created` stands in for the moment it was favourited -- every caller tests it for
     * truthiness, none of them reads the date. `date` and `originalDate` carry the one release
     * date the cache keeps, which is already the original one where the server knew it.
     */
    private fun songNode(track: Track): JSONObject {
        val node = JSONObject()
            .put("id", track.id)
            .put("isDir", false)
            .put("mediaType", "song")
            .put("type", track.type.orEmpty().ifBlank { "music" })
            .put("isCanonical", track.isCanonical)
        track.title?.let { node.put("title", it) }
        track.album?.let { node.put("album", it) }
        track.albumId?.let { node.put("albumId", it) }
        track.artist?.let { node.put("artist", it).put("displayArtist", it) }
        track.artistId?.let { node.put("artistId", it) }
        track.track?.let { node.put("track", it) }
        track.discNumber?.let { node.put("discNumber", it) }
        track.year?.let { node.put("year", it) }
        track.date?.let { node.put("date", it).put("originalDate", it) }
        track.coverArt?.let { node.put("coverArt", it) }
        track.size?.let { node.put("size", it) }
        track.suffix?.let { node.put("suffix", it) }
        track.contentType?.let { node.put("contentType", it) }
        track.transcodedSuffix?.let { node.put("transcodedSuffix", it) }
        track.transcodedContentType?.let { node.put("transcodedContentType", it) }
        track.duration?.let { node.put("duration", it) }
        track.bitRate?.let { node.put("bitRate", it) }
        track.path?.let { node.put("path", it) }
        track.userRating?.let { node.put("userRating", it) }
        track.workId?.let { node.put("workId", it) }
        track.versionKind?.let { node.put("versionKind", it) }
        track.created?.let { node.put("created", iso8601(it)) }
        if (track.starred) node.put("starred", iso8601(track.created ?: Date(0)))
        return node.putCollections(track)
    }

    private fun JSONObject.putCollections(track: Track): JSONObject {
        val genres = track.genreNames()
        if (genres.isNotEmpty()) put("genre", genres.joinToString(", "))
        put("genres", genres.jsonArray { JSONObject().put("name", it) })
        put("artists", track.artists.jsonArray { JSONObject().put("id", it.id).put("name", it.name) })
        put("moods", track.moods.jsonStrings())
        put("labels", track.labels.jsonStrings())
        return this
    }

    private fun albumNode(album: OfflineAlbum, withSongs: Boolean): JSONObject {
        val node = JSONObject()
            .put("id", album.id)
            .put("name", album.name)
            .put("mediaType", "album")
            .put("songCount", album.tracks.size)
            .put("duration", album.tracks.sumOf { it.duration ?: 0 })
        album.artist?.let { node.put("artist", it).put("displayArtist", it) }
        album.artistId?.let { node.put("artistId", it) }
        album.coverArt?.let { node.put("coverArt", it) }
        album.year?.let { node.put("year", it) }
        album.created?.let { node.put("created", iso8601(it)) }
        album.genres.firstOrNull()?.let { node.put("genre", it) }
        if (album.starred) node.put("starred", iso8601(album.created ?: Date(0)))
        node.put("genres", album.genres.jsonArray { JSONObject().put("name", it) })
        if (withSongs) node.put("song", album.tracks.jsonArray(::songNode))
        return node
    }

    /**
     * `getArtist` also answers with the artist's downloaded tracks that belong to no album, under
     * the `no_album` pseudo-album LMS invented for them, so an artist page offline shows
     * everything that can play rather than only what arrived in a release folder.
     */
    private fun artistNode(artist: OfflineArtist, withAlbums: Boolean): JSONObject {
        val albums = albums(artist.tracks)
        val node = JSONObject()
            .put("id", artist.id)
            .put("name", artist.name)
            .put("mediaType", "artist")
            .put("albumCount", albums.size)
            .put("songCount", artist.tracks.size)
        artist.coverArt?.let { node.put("coverArt", it) }
        if (artist.starred) node.put("starred", iso8601(artist.created ?: Date(0)))
        if (!withAlbums) return node

        val nodes = albums.sortedByDescending { it.created?.time ?: 0L }.jsonArray { albumNode(it, withSongs = false) }
        val loose = artist.tracks.filter { it.albumId.isNullOrBlank() }
        if (loose.isNotEmpty()) nodes.put(looseTracksNode(loose))
        return node.put("album", nodes)
    }

    private fun looseTracksNode(loose: List<Track>): JSONObject = JSONObject()
        .put("id", NO_ALBUM_ID)
        .put("name", "Other tracks")
        .put("isRealAlbum", false)
        .put("songCount", loose.size)
        .put("duration", loose.sumOf { it.duration ?: 0 })
        .put("coverArt", loose.firstNotNullOfOrNull { it.coverArt } ?: loose.first().id)
        .put("created", iso8601(loose.mapNotNull { it.created }.maxByOrNull { it.time } ?: Date(0)))
        .put("song", loose.jsonArray(::songNode))

    // ------------------------------------------------------------------------- envelope

    private fun ok(): JSONObject = envelope("ok")

    /**
     * LMS answers a missing cover with HTTP 404 and an empty body, which a bridge call has no way
     * of expressing; `70` is the Subsonic code for the same thing and is what every other
     * endpoint would have sent.
     */
    private fun notFound(): JSONObject = envelope("failed")
        .put("error", JSONObject().put("code", ERROR_NOT_FOUND).put("message", NOT_FOUND_MESSAGE))

    private fun envelope(status: String): JSONObject = JSONObject()
        .put("status", status)
        .put("version", PROTOCOL_VERSION)
        .put("type", SERVER_TYPE)
        .put("openSubsonic", true)

    // -------------------------------------------------------------------------- helpers

    private fun Track.genreNames(): List<String> = genres?.filter { it.isNotBlank() } ?: listOfNotNull(genre?.takeIf { it.isNotBlank() })

    /** `JSONArray` is not a `Collection`, so `mapTo` cannot fill one. */
    private fun <T> Iterable<T>.jsonArray(node: (T) -> JSONObject): JSONArray {
        val array = JSONArray()
        forEach { array.put(node(it)) }
        return array
    }

    private fun Iterable<String>.jsonStrings(): JSONArray {
        val array = JSONArray()
        forEach { array.put(it) }
        return array
    }

    private fun matches(track: Track, query: String): Boolean = matchesAll(query, track.title, track.artist, track.album)

    /** Every whitespace-separated keyword has to appear somewhere, which is what LMS does. */
    private fun matchesAll(query: String, vararg fields: String?): Boolean {
        val keywords = query.trim().split(WHITESPACE).filter { it.isNotBlank() }
        if (keywords.isEmpty()) return true
        val haystack = fields.filterNotNull().joinToString(" ").lowercase(Locale.ROOT)
        return keywords.all { haystack.contains(it.lowercase(Locale.ROOT)) }
    }

    private fun JSONObject.text(key: String): String? {
        if (!has(key) || isNull(key)) return null
        return optString(key).takeIf { it.isNotBlank() }
    }

    private fun JSONObject.number(key: String): Int? = text(key)?.trim()?.toDoubleOrNull()?.toInt()

    private fun JSONObject.flag(key: String): Boolean? = when (text(key)?.lowercase(Locale.ROOT)) {
        "1", "true" -> true
        "0", "false" -> false
        else -> null
    }

    companion object {
        const val RESPONSE = "subsonic-response"

        /** What LMS reports; the web only ever shows it, never parses it. */
        const val PROTOCOL_VERSION = "1.16.1"
        const val SERVER_TYPE = "lms"

        /** Subsonic's "the requested data was not found". */
        const val ERROR_NOT_FOUND = 70
        const val NOT_FOUND_MESSAGE = "The requested data was not found."

        /** The id LMS gives the pseudo-album holding an artist's tracks without a release. */
        const val NO_ALBUM_ID = "no_album"

        private const val SECONDS_PER_MINUTE = 60
        private const val DEFAULT_TRACK_COUNT = 50
        private const val DEFAULT_ALBUM_SIZE = 10
        private const val DEFAULT_ARTIST_SIZE = 100
        private const val DEFAULT_SEARCH_COUNT = 20

        private val WHITESPACE = Regex("\\s+")

        /** The format LMS writes its timestamps in, milliseconds included. */
        fun iso8601(date: Date): String = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.ROOT)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
            .format(date)
    }
}
