/*
 * PlaybackSourceHolder.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.content.SharedPreferences
import androidx.core.content.edit
import com.google.gson.Gson

/**
 * What the queue now playing was filled from.
 *
 * The "Recently played" grid is a list of places to go back to, not a list of tracks already heard,
 * so what has to be remembered is the *list* a queue came from rather than any track in it. Playing
 * one song out of Raw Hardstyle should put Raw Hardstyle in the grid, not that song and not its
 * album.
 *
 * A [HomeCard] is exactly the right thing to store: it already is the serializable form of "somewhere
 * in this app", and for a filtered list its `payload` carries the query itself. Replaying such a
 * shortcut therefore re-runs the search rather than replaying a frozen list of tracks -- different
 * songs, same corner of the library, which is the whole point.
 *
 * Persisted rather than kept in memory because playback outlives the process: a queue started
 * yesterday is still the queue that is playing after the app has been killed and restored.
 */
class PlaybackSourceHolder(private val preferences: SharedPreferences) {

    private val gson = Gson()

    /** Null when a queue has no place to go back to: shuffle-all, or a one-off search result. */
    fun set(card: HomeCard?) {
        preferences.edit {
            if (card == null) remove(KEY) else putString(KEY, gson.toJson(card))
        }
    }

    fun current(): HomeCard? {
        val json = preferences.getString(KEY, null) ?: return null

        // A half-written or hand-edited value must not stop the next play from being recorded.
        return try {
            gson.fromJson(json, HomeCard::class.java)
        } catch (_: Exception) {
            null
        }
    }

    private companion object {
        const val KEY = "home_playback_source"
    }
}
