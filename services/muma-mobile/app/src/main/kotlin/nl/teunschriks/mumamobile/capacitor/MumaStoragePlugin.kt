/*
 * MumaStoragePlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.os.Handler
import android.os.Looper
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.DownloadService
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.FileUtil.getCompleteFile
import nl.teunschriks.mumamobile.util.FileUtil.getPinnedFile
import nl.teunschriks.mumamobile.util.Storage
import org.json.JSONArray
import org.koin.core.component.KoinComponent
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
 * | `stateOf({ids})` | `DownloadService.getDownloadState(track)` per id, collapsed by [downloadStateWire] |
 * | `isLocal({id})` | whether a complete or pinned file exists |
 * | `download({ids, pin})` | `DownloadService.download(tracks, save = pin, updateSaveFlag = pin)` |
 * | `remove({ids})` | `DownloadService.unpin` then `DownloadService.delete` |
 * | `list()` | `DownloadService.observableDownloads` |
 * | `size()` | the bytes under the music directory |
 * | `query(request)` | **stub** — see [query] |
 * | `onProgress(fn)` | the `progress` event, from `RxBus.trackDownloadStatePublisher` |
 *
 * Every id has to become a whole [Track] first: the filename a download lives under is derived
 * from the title, artist, path and suffix (`FileUtil.getSongFile`), so an id alone cannot answer
 * a single one of these questions. [TrackLookup] does that, and an id this device has never seen
 * answers `none` / `false` rather than an error -- a list of a hundred rows must not fail because
 * one of them is new.
 */
@CapacitorPlugin(name = "MumaStorage")
class MumaStoragePlugin :
    Plugin(),
    KoinComponent {

    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val activeServerProvider: ActiveServerProvider by inject()

    private val lookup by lazy { TrackLookup(mediaPlayerManager, activeServerProvider) }
    private val main = Handler(Looper.getMainLooper())
    private val io = CoroutineScope(Dispatchers.IO)
    private val subscriptions = CompositeDisposable()

    override fun load() {
        subscriptions += RxBus.trackDownloadStateObservable.subscribe(
            { event ->
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
    }

    override fun handleOnDestroy() = subscriptions.clear()

    @PluginMethod
    fun stateOf(call: PluginCall) {
        val ids = stringsOf(call.getArray("ids"))
        withTracks(ids) { tracks ->
            val result = JSObject()
            ids.forEach { id ->
                val track = tracks[id]
                result.put(id, if (track == null) "none" else downloadStateWire(DownloadService.getDownloadState(track)))
            }
            call.resolve(result)
        }
    }

    @PluginMethod
    fun isLocal(call: PluginCall) {
        val id = call.getString("id").orEmpty()
        withTracks(listOf(id)) { tracks ->
            val track = tracks[id]
            call.resolve(JSObject().put("value", track != null && isOnDisk(track)))
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
        withTracks(ids) { tracks ->
            val found = ids.mapNotNull { tracks[it] }
            if (found.isNotEmpty()) DownloadService.download(found, save = pin, updateSaveFlag = pin)
            call.resolve(JSObject().put("requested", found.size).put("unknown", ids.size - found.size))
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
        withTracks(ids) { tracks ->
            val found = ids.mapNotNull { tracks[it] }
            DownloadService.unpin(found)
            DownloadService.delete(found)
            call.resolve(JSObject().put("removed", found.size))
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
        io.launch {
            val bytes = try {
                bytesUnder(FileUtil.musicDirectory)
            } catch (@Suppress("TooGenericExceptionCaught") all: Throwable) {
                Timber.w(all, "Failed to measure the download directory")
                0L
            }
            call.resolve(JSObject().put("value", bytes))
        }
    }

    /**
     * A Subsonic-shaped request answered from local files.
     *
     * **Phase 1 stub.** It answers the empty success body so a list component can call it without
     * a branch, and nothing more. TODO(phase 2): route this to `OfflineMusicService`, which
     * already answers these requests from Room and the files on disk, and return the body
     * `/rest` endpoint would have -- byte-identical, per the design's acceptance criterion 4.
     */
    @PluginMethod
    fun query(call: PluginCall) {
        call.resolve(JSObject().put("subsonic-response", JSObject().put("status", "ok")))
    }

    // ------------------------------------------------------------------ plumbing

    private fun isOnDisk(track: Track): Boolean = Storage.isPathExists(track.getCompleteFile()) || Storage.isPathExists(track.getPinnedFile())

    /**
     * Resolves the ids and hands them to [block] on the main thread, because everything the
     * callers do with them ends up in `DownloadService`, whose LiveData is main-thread bound.
     * The queue is read first (main thread, no IO) and only the remainder reaches Room.
     */
    private fun withTracks(ids: List<String>, block: (Map<String, Track>) -> Unit) {
        main.post {
            val queued = lookup.queued(ids)
            val missing = ids.filterNot { queued.containsKey(it) }
            if (missing.isEmpty()) {
                block(queued)
                return@post
            }
            io.launch {
                val cached = lookup.fromCache(missing)
                withContext(Dispatchers.Main) { block(queued + cached) }
            }
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
    }
}
