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
 *
 * A source belongs to one queue, which is why it is armed and then promoted rather than simply
 * written. A browse screen [arm]s itself just before it fills the queue; [startQueue] -- called
 * wherever a queue is actually replaced -- makes whatever was armed the source, and makes a queue
 * that armed nothing sourceless. Without that second step the last browse screen would stay the
 * source of every later play, whether it started from the home screen, from search, from the
 * notification or from the car, and the grid would never change again.
 */
class PlaybackSourceHolder(private val preferences: SharedPreferences) {

    private val gson = Gson()

    /**
     * Arms [card] as the source of the queue this screen is about to fill.
     *
     * Null for a screen that is no place to go back to: shuffle-all, a starred list, a shared link.
     */
    fun arm(card: HomeCard?) {
        preferences.edit {
            if (card == null) remove(KEY_ARMED) else putString(KEY_ARMED, gson.toJson(card))
        }
    }

    /**
     * A queue was just replaced: whatever was armed is now the source, and nothing armed means this
     * queue has none.
     */
    fun startQueue() {
        val armed = preferences.getString(KEY_ARMED, null)

        preferences.edit {
            remove(KEY_ARMED)
            if (armed == null) remove(KEY_CURRENT) else putString(KEY_CURRENT, armed)
        }
    }

    fun current(): HomeCard? {
        val json = preferences.getString(KEY_CURRENT, null) ?: return null

        // A half-written or hand-edited value must not stop the next play from being recorded.
        return try {
            gson.fromJson(json, HomeCard::class.java)
        } catch (_: Exception) {
            null
        }
    }

    private companion object {
        const val KEY_CURRENT = "home_playback_source"
        const val KEY_ARMED = "home_playback_source_armed"
    }
}
