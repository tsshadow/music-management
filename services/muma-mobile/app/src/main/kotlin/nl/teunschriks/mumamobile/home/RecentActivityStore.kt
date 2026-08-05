/*
 * RecentActivityStore.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.content.SharedPreferences
import androidx.core.content.edit
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import nl.teunschriks.mumamobile.util.Settings

/**
 * Most-recently-used list of home screen shortcuts.
 *
 * Whole cards are stored rather than ids, so the shortcuts grid renders immediately and offline
 * without a network call per item.
 *
 * Items are recorded when the user *opens* them, and, through [PlayHistoryRecorder], when a track
 * is actually played: a session driven from Android Auto or the notification never touches a
 * browse screen, and used to leave the grid showing whatever was last opened by hand.
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

    /**
     * Fills in the cover art of an already stored card.
     *
     * A card is written once, when it is opened, so one that was stored without artwork -- an
     * artist the server had no picture for at the time -- would otherwise keep its blank forever.
     * Reads and writes the whole history rather than the visible slice, so entries past the
     * shortcuts grid are not dropped.
     */
    fun updateCoverArt(cardKey: String, coverArtId: String, setsMode: Boolean) {
        val key = keyFor(setsMode)
        val cards = read(key)
        val index = cards.indexOfFirst { it.key == cardKey }

        if (index == -1) return

        cards[index] = cards[index].copy(coverArtId = coverArtId)
        preferences.edit { putString(key, gson.toJson(cards)) }
    }

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
