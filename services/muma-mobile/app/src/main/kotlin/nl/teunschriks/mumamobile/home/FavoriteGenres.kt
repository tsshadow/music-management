/*
 * FavoriteGenres.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.isUsableMumaUserId
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.util.Settings
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * The genres the user pinned, shared with the web player.
 *
 * The web UI keeps its favorites in the MuMa per-app settings blob under `app_id = "frontend"`, as
 * `{"favoriteGenres": [...]}`. Reading and writing that same key means one list across devices
 * without a new endpoint or table. [Settings.favoriteGenres] is the local copy, so the list is
 * available offline, on the Android Auto browser's thread, and before the first sync completes.
 *
 * Both network calls block; call them off the main thread.
 */
object FavoriteGenres : KoinComponent {

    private const val APP_ID = "frontend"

    private val activeServerProvider: ActiveServerProvider by inject()

    /** The local copy. Cheap, never throws, safe on any thread. */
    fun current(): List<String> = parseFavoriteGenres(Settings.favoriteGenres)

    fun isFavorite(genre: String): Boolean = current().contains(genre)

    /**
     * Adds or removes [genre] locally, then pushes the whole list (only the `favoriteGenres` key of
     * the blob; every other key is the server's to keep). Returns its new state.
     *
     * A failed push is logged and swallowed: the local list stays changed and the next toggle
     * sends it again in full, so a temporary outage costs a round trip, not the edit.
     */
    fun toggle(genre: String): Boolean {
        val favorites = current().toMutableList()
        val added = !favorites.remove(genre)
        if (added) favorites.add(genre)

        favorites.sort()
        Settings.favoriteGenres = Gson().toJson(favorites)
        push(favorites)

        return added
    }

    /**
     * Takes the server's list, or seeds the server with the local one when it has none — which is
     * what happens on the first run and after favoriting something while offline.
     */
    fun pull() {
        val userId = userId() ?: return

        try {
            val blob = getMusicService().getMumaSettings(userId, APP_ID)
            val remote = readFavoriteGenres(blob)

            if (remote == null) {
                push(current())
            } else {
                Settings.favoriteGenres = Gson().toJson(remote)
            }
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            Timber.w(e, "Could not read favorite genres from MuMa")
        }
    }

    private fun push(favorites: List<String>) {
        val userId = userId() ?: return

        try {
            getMusicService().patchMumaSettings(userId, APP_ID, favoriteGenresChange(favorites))
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            Timber.w(e, "Could not save favorite genres to MuMa")
        }
    }

    /** Null whenever syncing is impossible, which leaves the local list authoritative. */
    private fun userId(): Int? {
        if (ActiveServerProvider.isOffline()) return null

        val userId = activeServerProvider.getActiveServer().mumaUserId ?: Settings.mumaUserId
        return userId.takeIf { isUsableMumaUserId(it) }
    }
}

/** Parses the local `["a","b"]` copy. */
internal fun parseFavoriteGenres(json: String): List<String> = try {
    JsonParser.parseString(json).asJsonArray.mapNotNull { it.asStringOrNull() }
} catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
    Timber.w(e, "Malformed local favorite genres, starting empty")
    emptyList()
}

/**
 * The favorites inside a MuMa settings blob, or null when the blob has no `favoriteGenres` key —
 * which is a different thing from an empty list, and the caller treats it differently.
 */
internal fun readFavoriteGenres(blob: String?): List<String>? {
    val root = blob?.let { parseObjectOrNull(it) } ?: return null
    val array = root.get(KEY_FAVORITE_GENRES) as? JsonArray ?: return null

    return array.mapNotNull { it.asStringOrNull() }
}

/**
 * The per-key settings change that stores [favorites]: `{"favoriteGenres": [...]}` and nothing
 * else. The server merges it into the blob, so whatever the web UI or another device keeps next to
 * this key is never read, carried along or written back from here (issue #39).
 */
internal fun favoriteGenresChange(favorites: List<String>): String {
    val array = JsonArray().apply { favorites.forEach { add(it) } }
    return JsonObject().apply { add(KEY_FAVORITE_GENRES, array) }.toString()
}

private const val KEY_FAVORITE_GENRES = "favoriteGenres"

private fun parseObjectOrNull(blob: String): JsonObject? = try {
    JsonParser.parseString(blob) as? JsonObject
} catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
    Timber.w(e, "Malformed MuMa settings blob, treating it as empty")
    null
}

private fun com.google.gson.JsonElement.asStringOrNull(): String? = if (isJsonPrimitive) asString else null
