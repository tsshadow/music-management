/*
 * MumaStoragePlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Handler
import android.os.Looper
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import io.reactivex.rxjava3.disposables.CompositeDisposable
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.DownloadService
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.CacheCleaner
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.FileUtil.getCompleteFile
import nl.teunschriks.mumamobile.util.FileUtil.getPinnedFile
import nl.teunschriks.mumamobile.util.Storage
import org.json.JSONArray
import org.json.JSONObject
import org.koin.core.component.KoinComponent
import org.koin.core.component.get
import org.koin.core.component.inject
import timber.log.Timber

/**
 * `platform.storage` — music kept on the device.
 *
 * Implements the `PlatformStorage` typedef of `services/frontend/src/lib/platform/index.js` on top
 * of [DownloadService], which is a static, `Context`-only companion: there is no instance to
 * inject and no lifecycle to manage here, only calls.
 *
 * | JS | Kotlin |
 * |---|---|
 * | `stateOf({ids})` | one Room query for the ids, then `DownloadService.getDownloadState` per track |
 * | `isLocal({id})` | whether a complete or pinned file exists |
 * | `download({ids, pin})` | `DownloadService.download(tracks, save = pin, updateSaveFlag = pin)` |
 * | `remove({ids})` | `DownloadService.unpin` then `DownloadService.delete` |
 * | `list()` | `DownloadService.observableDownloads` |
 * | `size()` | the bytes under the music directory |
 * | `query({method, params})` | [OfflineSubsonic] over the Room cache and the files on disk |
 * | `isOffline()` | [hasRouteToServer], the same test the Kotlin services make |
 * | `checkServer({timeoutMs})` | one `ping` within the budget, classified by [ServerReachability] |
 * | `setOfflineMode({enabled})` | [ServerReachability.offlineChosen] |
 * | `onProgress(fn)` | the `progress` event, from `RxBus.trackDownloadStatePublisher` |
 * | `onConnectivity(fn)` | the `connectivity` event, from a `ConnectivityManager` callback |
 * | `clearCache()` | cancels queued/active downloads, then [CacheCleaner.clearCache] |
 *
 * Every id has to become a whole [Track] first: the filename a download lives under is derived
 * from the title, artist, path and suffix (`FileUtil.getSongFile`), so an id alone cannot answer
 * a single one of these questions. [TrackLookup] does that, and an id this device has never seen
 * answers `none` / `false` rather than an error -- a list of a hundred rows must not fail because
 * one of them is new.
 *
 * ### Threading
 *
 * `query` reads Room and stats files, so it runs on [io] and resolves back on the main thread,
 * which is the thread the bridge marshals from. `stateOf` does the same for its file checks: a
 * list of two hundred rows is two hundred `Storage.isPathExists` calls, and those have no
 * business on the thread that draws.
 */
@CapacitorPlugin(name = "MumaStorage")
class MumaStoragePlugin :
    Plugin(),
    KoinComponent {

    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val activeServerProvider: ActiveServerProvider by inject()
    private val cacheCleaner: CacheCleaner by inject()

    private val lookup by lazy { TrackLookup(mediaPlayerManager, activeServerProvider) }
    private val main = Handler(Looper.getMainLooper())
    private val calls = PluginCallScope("MumaStorage")
    private val subscriptions = CompositeDisposable()

    /**
     * The downloaded library as Subsonic bodies. Built once: it memoises the on-disk set, which
     * is what keeps a screenful of calls from restatting every file, and only a download state
     * change may drop that memo.
     */
    private val offline by lazy {
        OfflineSubsonic(
            allTracks = { activeServerProvider.getActiveMetaDatabase().trackDao().get() },
            onDisk = ::isOnDisk,
            coverArtUrl = ::localCoverArtUrl,
            playlists = ::offlinePlaylists
        )
    }

    /**
     * Every playlist this device remembers for the active server: the `offline_playlists` Room
     * rows [nl.teunschriks.mumamobile.service.RESTMusicService] writes on every playlist fetch,
     * plus any `.m3u` file downloaded before that table existed -- see [LegacyPlaylistFiles].
     */
    private fun offlinePlaylists(): List<OfflineSubsonic.PlaylistRecord> {
        val database = activeServerProvider.getActiveMetaDatabase()
        val stored = database.offlinePlaylistDao().get().map {
            OfflineSubsonic.PlaylistRecord(id = it.id, name = it.name, trackIds = it.trackIds)
        }
        val legacy = LegacyPlaylistFiles.read(
            directory = FileUtil.getPlaylistDirectory(activeServerProvider.getActiveServer().name),
            knownNames = stored.map { it.name }.toSet(),
            tracks = database.trackDao().get()
        )
        return stored + legacy
    }

    private val connectivity: ConnectivityManager?
        get() = context?.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun load() {
        subscriptions += RxBus.trackDownloadStateObservable.subscribe(
            { event ->
                offline.invalidate()
                notifyListeners(
                    EVENT_PROGRESS,
                    JSObject()
                        .put("id", event.id)
                        .put("state", downloadStateWire(event.state))
                        .put("progress", event.progress ?: 0)
                )
            },
            { Timber.w(it, "download state stream failed") }
        )
        watchConnectivity()
    }

    override fun handleOnDestroy() {
        subscriptions.clear()
        unwatchConnectivity()
        calls.cancel()
    }

    @PluginMethod
    fun stateOf(call: PluginCall) {
        val ids = stringsOf(call.getArray("ids"))
        withTracks(call, ids) { tracks, answer ->
            calls.runCall(answer) {
                val result = JSObject()
                ids.forEach { id ->
                    val track = tracks[id]
                    result.put(id, if (track == null) "none" else downloadStateWire(DownloadService.getDownloadState(track)))
                }
                withContext(Dispatchers.Main) { answer.resolve(result) }
            }
        }
    }

    @PluginMethod
    fun isLocal(call: PluginCall) {
        val id = call.getString("id").orEmpty()
        withTracks(call, listOf(id)) { tracks, answer ->
            val track = tracks[id]
            answer.resolve(JSObject().put("value", track != null && isOnDisk(track)))
        }
    }

    /**
     * @param pin whether the files survive a cache sweep. `false` downloads into the cache, which
     *   is what the legacy UI's "download" does; `true` is its "pin".
     */
    @PluginMethod
    fun download(call: PluginCall) {
        val ids = stringsOf(call.getArray("ids"))
        val pin = call.getBoolean("pin", false) == true
        withTracks(call, ids) { tracks, answer ->
            val found = ids.mapNotNull { tracks[it] }
            if (found.isNotEmpty()) DownloadService.download(found, save = pin, updateSaveFlag = pin)
            answer.resolve(JSObject().put("requested", found.size).put("unknown", ids.size - found.size))
        }
    }

    /**
     * Unpins first, then deletes. A pinned file is renamed back into the cache by `unpin` and the
     * delete then removes every copy; deleting a pinned track without unpinning it leaves the save
     * flag set, and the next queue fill downloads it again.
     */
    @PluginMethod
    fun remove(call: PluginCall) {
        val ids = stringsOf(call.getArray("ids"))
        withTracks(call, ids) { tracks, answer ->
            val found = ids.mapNotNull { tracks[it] }
            DownloadService.unpin(found)
            DownloadService.delete(found)
            offline.invalidate()
            answer.resolve(JSObject().put("removed", found.size))
        }
    }

    @PluginMethod
    fun list(call: PluginCall) = main.post {
        val tracks = DownloadService.observableDownloads.value.orEmpty()
        val array = JSONArray()
        tracks.forEach { track ->
            array.put(
                JSObject()
                    .put("id", track.id)
                    .put("title", track.title)
                    .put("artist", track.artist)
                    .put("album", track.album)
                    .put("duration", track.duration)
                    .put("state", downloadStateWire(DownloadService.getDownloadState(track)))
            )
        }
        call.resolve(JSObject().put("items", array))
    }

    @PluginMethod
    fun size(call: PluginCall) {
        calls.runCall(call) { answer ->
            val bytes = try {
                bytesUnder(FileUtil.musicDirectory)
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                Timber.w(all, "Failed to measure the download directory")
                0L
            }
            answer.resolve(JSObject().put("value", bytes))
        }
    }

    /**
     * The device-settings screen's "Clear cache": cancels whatever is queued or downloading, then
     * deletes every cached file that is not pinned and not part of the current playlist. Pinned
     * files are never at risk -- [CacheCleaner.clearCache] only ever matches the ".partial" and
     * ".complete" suffixes a pin is renamed away from.
     */
    @PluginMethod
    fun clearCache(call: PluginCall) {
        DownloadService.clearDownloads()
        cacheCleaner.clearCache()
        offline.invalidate()
        call.resolve()
    }

    /**
     * A Subsonic-shaped request answered from local files.
     *
     * `{method, params}` in, the body `/rest/<method>` would have answered with out. The method
     * names this understands are the ones the web player actually calls -- see [OfflineSubsonic];
     * anything else answers the empty success body, so a list component can call this without a
     * branch and without a failure path.
     *
     * `getCoverArt` is the exception that is not JSON on the server. It answers `{status, url}`
     * with an address the WebView loads by itself. Nothing streams through the bridge: playback
     * of a cached file never reaches the WebView at all, because `MumaPlayer.load`/`setQueue`
     * resolve local files natively, which is why `stream` is not implemented here.
     */
    @PluginMethod
    fun query(call: PluginCall) {
        val method = call.getString("method").orEmpty()
        val params: JSONObject = call.getObject("params") ?: JSObject()
        calls.runCall(call) { answer ->
            val body = try {
                offline.answer(method, params)
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                Timber.w(all, "Offline query for %s failed", method)
                JSONObject().put(OfflineSubsonic.RESPONSE, JSONObject().put("status", "ok"))
            }
            withContext(Dispatchers.Main) { answer.resolve(JSObject.fromJSONObject(body)) }
        }
    }

    /**
     * Whether the device has no route to the server, so the web UI can pick its data source.
     *
     * Advisory rather than a promise: a network with internet capability can still fail to reach
     * a server on the listener's own LAN. The UI is expected to try the server first and fall
     * back on a failure; this only spares it from trying at all when there is plainly no point.
     */
    @PluginMethod
    fun isOffline(call: PluginCall) {
        call.resolve(JSObject().put("value", !online()))
    }

    /**
     * The start-up check (docs/designs/app-start-reachability/): one Subsonic `ping`, signed by the
     * app's own client, within `timeoutMs` (default [ServerReachability.DEFAULT_TIMEOUT_MS]),
     * classified together with Android's network state by [ServerReachability.classify].
     *
     * Resolves `{state, elapsedMs, offlineChosen}`; `state` is a [Reachability.wire] value. Never
     * rejects on a failed ping -- a ping that failed is the answer. With the hand-picked offline
     * library active there is no server to ask, and the answer rests on the network state alone.
     */
    @PluginMethod
    fun checkServer(call: PluginCall) {
        val timeoutMs = (call.getInt("timeoutMs") ?: ServerReachability.DEFAULT_TIMEOUT_MS.toInt()).toLong()
        calls.runCall(call) { answer ->
            val started = System.nanoTime()
            val networkUp = connectivity?.hasInternetCapability() == true
            val outcome = if (ActiveServerProvider.isOffline()) {
                null
            } else {
                pingWithin(get<SubsonicAPIClient>().api.ping(), timeoutMs)
            }
            val state = ServerReachability.classify(networkUp, outcome)
            val elapsedMs = (System.nanoTime() - started) / NANOS_PER_MILLI
            Timber.i("Start-up check: %s (%s) in %d ms", state, outcome, elapsedMs)
            withContext(Dispatchers.Main) {
                answer.resolve(
                    JSObject()
                        .put("state", state.wire)
                        .put("elapsedMs", elapsedMs)
                        .put("offlineChosen", ServerReachability.offlineChosen)
                )
            }
        }
    }

    /**
     * "Offline verder" on (`{enabled: true}`) or off. While on, [isOffline] answers true whatever
     * the network does and `MusicServiceFactory` hands out the offline service, so the web UI,
     * the native services and the Android Auto tree agree. A `connectivity` event follows.
     */
    @PluginMethod
    fun setOfflineMode(call: PluginCall) {
        ServerReachability.offlineChosen = call.getBoolean("enabled", false) == true
        Timber.i("Offline mode %s", if (ServerReachability.offlineChosen) "chosen" else "left")
        emitConnectivity(online())
        call.resolve()
    }

    // ------------------------------------------------------------------ plumbing

    private fun online(): Boolean = hasRouteToServer(
        activeServerIsOfflineDb = ActiveServerProvider.isOffline(),
        networkHasInternet = connectivity?.hasInternetCapability() == true,
        offlineChosen = ServerReachability.offlineChosen
    )

    /**
     * A `connectivity` event per network change, and one straight away so the UI never has to
     * guess before the first change arrives.
     */
    private fun watchConnectivity() {
        emitConnectivity(online())
        val manager = connectivity ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = emitConnectivity(
                !ActiveServerProvider.isOffline() && !ServerReachability.offlineChosen
            )

            override fun onLost(network: Network) = emitConnectivity(online())
        }
        try {
            manager.registerNetworkCallback(
                NetworkRequest.Builder().addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build(),
                callback
            )
            networkCallback = callback
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Could not watch connectivity; the web UI polls isOffline instead")
        }
    }

    private fun unwatchConnectivity() {
        val callback = networkCallback ?: return
        networkCallback = null
        try {
            connectivity?.unregisterNetworkCallback(callback)
        } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
            Timber.w(all, "Could not stop watching connectivity")
        }
    }

    private fun emitConnectivity(online: Boolean) {
        notifyListeners(EVENT_CONNECTIVITY, JSObject().put("online", online))
    }

    private fun isOnDisk(track: Track): Boolean = Storage.isPathExists(track.getCompleteFile()) || Storage.isPathExists(track.getPinnedFile())

    /**
     * The artwork this device already has, as an address the WebView may load.
     *
     * Capacitor serves any file under `<local url>/_capacitor_file_/<absolute path>`, which is
     * what `Capacitor.convertFileSrc` builds on the JS side; an `<img src>` pointing at it is an
     * ordinary request to the local server rather than a bridge round trip per row. The cover
     * cache is keyed by album directory, not by the server's art id, so this resolves through the
     * track. A cover the app never fetched has no file and no URL: the caller answers 70.
     */
    private fun localCoverArtUrl(track: Track): String? {
        val key = FileUtil.getAlbumArtKey(track, true) ?: return null
        val file = File(FileUtil.getAlbumArtFile(key))
        if (!file.isFile || file.length() == 0L) return null
        val base = bridge?.localUrl?.trimEnd('/') ?: return null
        return base + CAPACITOR_FILE_PREFIX + file.absolutePath
    }

    /**
     * Resolves the ids and hands them to [block] on the main thread, because everything the
     * callers do with them ends up in `DownloadService`, whose LiveData is main-thread bound.
     * The queue is read first (main thread, no IO) and only the remainder reaches Room.
     *
     * [block] answers through the [CallAnswer] it is given; a failure anywhere on the way,
     * the Room lookup included, rejects [call] instead of leaving its promise pending.
     */
    private fun withTracks(call: PluginCall, ids: List<String>, block: (Map<String, Track>, CallAnswer) -> Unit) {
        val answer = CallAnswer(call)
        main.post {
            val queued = try {
                lookup.queued(ids)
            } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
                Timber.w(failure, "Could not read the queue for %s", ids)
                answer.reject(failure.message ?: failure.javaClass.simpleName)
                return@post
            }
            val missing = ids.filterNot { queued.containsKey(it) }
            if (missing.isEmpty()) {
                runBlockSafely(answer) { block(queued, answer) }
                return@post
            }
            calls.runCall(answer) {
                val cached = lookup.fromCache(missing)
                withContext(Dispatchers.Main) { block(queued + cached, answer) }
            }
        }
    }

    /** Runs [block] on the calling thread, rejecting [answer] if it throws. */
    private fun runBlockSafely(answer: CallAnswer, block: () -> Unit) {
        try {
            block()
        } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
            Timber.w(failure, "Storage call failed")
            answer.reject(failure.message ?: failure.javaClass.simpleName)
        }
    }

    private fun stringsOf(array: JSONArray?): List<String> {
        if (array == null) return emptyList()
        return (0 until array.length()).mapNotNull { array.optString(it).takeIf { s -> s.isNotBlank() } }
    }

    private fun bytesUnder(file: nl.teunschriks.mumamobile.util.AbstractFile): Long = when {
        file.isFile -> file.length
        file.isDirectory -> FileUtil.listFiles(file).sumOf { bytesUnder(it) }
        else -> 0L
    }

    companion object {
        const val EVENT_PROGRESS = "progress"
        const val EVENT_CONNECTIVITY = "connectivity"

        private const val NANOS_PER_MILLI = 1_000_000L

        /** Capacitor's local file route; the JS side reaches it through `Capacitor.convertFileSrc`. */
        const val CAPACITOR_FILE_PREFIX = "/_capacitor_file_"
    }
}
