/*
 * BookmarkMigration.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.isUsableMumaUserId
import nl.teunschriks.mumamobile.domain.Bookmark
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.Settings
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * One-time push of this account's Subsonic bookmarks into the web's `setResume` account-settings
 * key -- the generalisation the functional design asks for ("Sets" table, "Resume" row: "the
 * phone's bookmarks feature, generalised; the reason bookmarks need no screen of their own").
 *
 * Bookmarks were never stored on the phone: [PlayerFragment]'s bookmark menu and
 * [TrackInfoModalFragment] call [MusicService.createBookmark]/`deleteBookmark` straight through to
 * the Subsonic server, and the only local trace is `Track.bookmarkPosition`, refreshed from the
 * server on every directory fetch. So this reads the server's list once rather than a local table,
 * and writes the same per-work map `services/frontend/src/lib/setResume.js` reads on play, keyed
 * the same way (`resumeKeyFor`, mirroring `getDeduplicateKey` in `deduplicate.js`) -- a bookmark set
 * from the old phone screen resumes on the web exactly like a position the web itself saved.
 *
 * Runs once per account ([Settings.bookmarksMigratedToSetResume]), from
 * `CapacitorActivity.onCreate` -- the shell's bootstrap. Both network calls block; callers run this
 * off the main thread.
 */
object BookmarkMigration : KoinComponent {

    private const val APP_ID = "frontend"

    /** The same songs/sets boundary the web uses (`downloads.js`'s `SET_SECONDS`). */
    private const val SET_SECONDS = 600

    private val activeServerProvider: ActiveServerProvider by inject()

    /**
     * Migrates this account's bookmarks, unless it already has, there is nobody signed in to MuMa,
     * or there is no connection right now.
     *
     * Safe to call on every launch: the flag makes every call after the first a no-op, and any
     * failure -- offline, no MuMa account yet, a server error -- leaves the flag untouched so the
     * next launch tries again rather than silently giving up on this account forever.
     */
    fun runOnce() {
        if (Settings.bookmarksMigratedToSetResume) return
        if (ActiveServerProvider.isOffline()) return

        val userId = activeServerProvider.getActiveServer().mumaUserId ?: Settings.mumaUserId
        if (!isUsableMumaUserId(userId)) return

        try {
            val service = getMusicService()
            val setBookmarks = service.getBookmarks().filter { isSet(it) }

            if (setBookmarks.isNotEmpty()) {
                val merged = mergeSetResume(service.getMumaSettings(userId, APP_ID), setBookmarks)
                service.saveMumaSettings(userId, APP_ID, merged)
            }
            Settings.bookmarksMigratedToSetResume = true
            Timber.i("Migrated ${setBookmarks.size} bookmark(s) into setResume")
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            Timber.w(e, "Could not migrate bookmarks into setResume; will retry next launch")
        }
    }

    private fun isSet(bookmark: Bookmark): Boolean = (bookmark.track.duration ?: 0) >= SET_SECONDS
}

/**
 * The resume key a bookmark's track resolves to: `work:<id>` when MuMa has grouped it,
 * `track:<id>` otherwise -- the same fallback `getDeduplicateKey`
 * (`services/frontend/src/lib/deduplicate.js`) uses, so a bookmark on an ungrouped file still
 * lands under the key the web will use for it once it is.
 */
internal fun resumeKeyFor(bookmark: Bookmark): String {
    val workId = bookmark.track.workId
    return if (workId != null && workId > 0) "work:$workId" else "track:${bookmark.track.id}"
}

/**
 * Puts every bookmark into [blob]'s `setResume` map and caps it at [MAX_SET_RESUME_ENTRIES],
 * exactly like the web's own throttled writes -- a bookmark is a resume position by another name,
 * so migrating it and the web writing one for the same set afterwards are safe to race; whichever
 * `updatedAt` is newer stays.
 *
 * Every other key already in the blob (favourite genres, the interface language, device settings)
 * is kept: the backend overwrites the whole blob on write, so anything the web or another migration
 * stored next to `setResume` has to be carried over rather than dropped.
 */
internal fun mergeSetResume(blob: String?, bookmarks: List<Bookmark>): String {
    val root = blob?.let { parseObjectOrNull(it) } ?: JsonObject()
    val setResume = (root.get(KEY_SET_RESUME) as? JsonObject)?.deepCopy() ?: JsonObject()

    for (bookmark in bookmarks) {
        val key = resumeKeyFor(bookmark)
        val updatedAt = bookmark.changed?.time ?: bookmark.created?.time ?: System.currentTimeMillis()
        val existing = setResume.get(key) as? JsonObject
        if (existing != null && (existing.get("updatedAt")?.asLong ?: 0L) >= updatedAt) continue

        val entry = JsonObject().apply {
            addProperty("position", bookmark.position / MILLIS_PER_SECOND)
            addProperty("updatedAt", updatedAt)
        }
        setResume.add(key, entry)
    }

    root.add(KEY_SET_RESUME, capped(setResume))
    return root.toString()
}

private const val MILLIS_PER_SECOND = 1000
private const val MAX_SET_RESUME_ENTRIES = 50
private const val KEY_SET_RESUME = "setResume"

/** Keeps only the most recently updated entries, mirroring `setResume.js`'s own cap. */
private fun capped(setResume: JsonObject): JsonObject {
    val entries = setResume.entrySet().toList()
    if (entries.size <= MAX_SET_RESUME_ENTRIES) return setResume

    val kept = entries.sortedByDescending { (_, value) ->
        (value as? JsonObject)?.get("updatedAt")?.asLong ?: 0L
    }.take(MAX_SET_RESUME_ENTRIES)

    val result = JsonObject()
    kept.forEach { (key, value) -> result.add(key, value) }
    return result
}

private fun parseObjectOrNull(blob: String): JsonObject? = try {
    JsonParser.parseString(blob) as? JsonObject
} catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
    Timber.w(e, "Malformed MuMa settings blob, treating it as empty")
    null
}
