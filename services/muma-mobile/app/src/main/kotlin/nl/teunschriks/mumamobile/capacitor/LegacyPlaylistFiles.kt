/*
 * LegacyPlaylistFiles.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import java.io.File
import java.security.MessageDigest
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.FileUtil.getCompleteFile
import nl.teunschriks.mumamobile.util.FileUtil.getPartialFile
import nl.teunschriks.mumamobile.util.FileUtil.getPinnedFile

/**
 * The playlists a phone downloaded before it started remembering a playlist's server id (see
 * [OfflinePlaylist][nl.teunschriks.mumamobile.domain.OfflinePlaylist]).
 *
 * `RESTMusicService.getPlaylist` writes one `.m3u` file per playlist under the active server's
 * playlist directory, and always did -- one line per track, the path [FileUtil.getSongFile] would
 * give it. Nothing about that file names the playlist beyond its filename, so a device that has
 * only ever seen the old format cannot answer [OfflineSubsonic.PlaylistRecord] for it from Room
 * alone. Read here instead: each file becomes a record under a synthetic id derived from its own
 * path, and each line is matched back to a track by comparing it against the same paths
 * [FileUtil] would have written for every track this device knows about.
 *
 * A device that has since re-fetched a playlist has both a Room row and this file for it; the
 * caller passes that row's name in [knownNames] so the same playlist is not offered twice.
 */
object LegacyPlaylistFiles {

    /**
     * @param directory the active server's playlist directory (`FileUtil.getPlaylistDirectory`).
     * @param knownNames the name of every playlist already covered by a Room row, so its `.m3u`
     *   file is not turned into a second, id-less listing of the same playlist.
     * @param tracks every track the per-server Room cache holds, to resolve a line back to an id.
     */
    fun read(directory: File, knownNames: Set<String>, tracks: List<Track>): List<OfflineSubsonic.PlaylistRecord> {
        val files = directory.listFiles { file -> file.isFile && FileUtil.isPlaylistFile(file) } ?: return emptyList()
        val byPath = pathIndex(tracks)
        return files
            .filterNot { FileUtil.getBaseName(it.name) in knownNames }
            .map { record(it, byPath) }
    }

    private fun pathIndex(tracks: List<Track>): Map<String, String> {
        val byPath = HashMap<String, String>()
        tracks.forEach { track ->
            byPath[FileUtil.getSongFile(track)] = track.id
            byPath[track.getCompleteFile()] = track.id
            byPath[track.getPinnedFile()] = track.id
            byPath[track.getPartialFile()] = track.id
        }
        return byPath
    }

    private fun record(file: File, byPath: Map<String, String>): OfflineSubsonic.PlaylistRecord {
        val trackIds = file.readLines()
            .map { it.trim() }
            .filterNot { it.isEmpty() || it == "#EXTM3U" }
            .mapNotNull { byPath[it] }
        return OfflineSubsonic.PlaylistRecord(id = syntheticId(file), name = FileUtil.getBaseName(file.name), trackIds = trackIds)
    }

    /**
     * Stable across calls -- the web keeps a playlist's id as a cache key -- and derived from the
     * file's own path rather than its display name, which a listener could rename.
     */
    private fun syntheticId(file: File): String {
        val digest = MessageDigest.getInstance("SHA-1").digest(file.absolutePath.toByteArray())
        return LEGACY_ID_PREFIX + digest.joinToString("") { "%02x".format(it) }.take(SYNTHETIC_ID_LENGTH)
    }

    private const val LEGACY_ID_PREFIX = "legacy:"
    private const val SYNTHETIC_ID_LENGTH = 16
}
