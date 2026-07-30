/*
 * RecentActivityStore.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import android.content.SharedPreferences
import androidx.core.content.edit
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import org.moire.ultrasonic.util.Settings

/**
 * Most-recently-used list of home screen shortcuts.
 *
 * Whole cards are stored rather than ids, so the shortcuts grid renders immediately and offline
 * without a network call per item.
 *
 * Items are recorded when the user *opens* them; playing from inside an album, artist or playlist
 * implies having opened it, so playback itself records nothing.
 */
class RecentActivityStore(
    private val preferences: SharedPreferences,
    private val separatePerMode: () -> Boolean = { Settings.separateHomeHistoryPerMode }
) {
    private val gson = Gson()
    private val listType = object : TypeToken<MutableList<HomeCard>>() {}.type

    fun record(card: HomeCard, setsMode: Boolean) {
        val key = keyFor(setsMode)
        val cards = read(key)

        cards.removeAll { it.key == card.key }
        cards.add(0, card)
        while (cards.size > MAX_ENTRIES) cards.removeAt(cards.size - 1)

        preferences.edit { putString(key, gson.toJson(cards)) }
    }

    fun recent(setsMode: Boolean, limit: Int = DEFAULT_LIMIT): List<HomeCard> =
        read(keyFor(setsMode)).take(limit)

    private fun keyFor(setsMode: Boolean): String = when {
        !separatePerMode() -> KEY_SHARED
        setsMode -> KEY_SETS
        else -> KEY_SONGS
    }

    private fun read(key: String): MutableList<HomeCard> = try {
        gson.fromJson<MutableList<HomeCard>>(preferences.getString(key, "[]"), listType)
            ?: mutableListOf()
    } catch (_: Exception) {
        // A corrupt or half-written history must never keep the home screen from loading.
        mutableListOf()
    }

    companion object {
        const val MAX_ENTRIES = 24
        const val DEFAULT_LIMIT = 8

        private const val KEY_SONGS = "home_recent_songs"
        private const val KEY_SETS = "home_recent_sets"
        private const val KEY_SHARED = "home_recent_shared"
    }
}
