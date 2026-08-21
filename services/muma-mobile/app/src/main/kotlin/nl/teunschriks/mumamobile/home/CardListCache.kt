/*
 * CardListCache.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.content.SharedPreferences
import androidx.core.content.edit
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * The last known contents of a home section or browse page, kept across restarts.
 *
 * Every list on those screens was already cached, but only in memory: the caches in
 * `CachedMusicService` die with the process, so each cold start redrew skeletons for data that had
 * not changed since the app was last closed. This stores the finished product -- the cards a
 * section renders -- so the screen can put them up at once and refresh behind them.
 *
 * Only the cards are stored. A section's title is a string resource id, and those are renumbered
 * between builds, so a cached one would eventually resolve to the wrong heading; titles stay with
 * the provider that owns them.
 *
 * [scope] prefixes every key with the active server and mode, so switching either is a miss rather
 * than a wrong answer. It is a lambda because reading those means touching global state, and
 * keeping that out of here is what lets this class be tested as plain Kotlin.
 */
class CardListCache(
    private val preferences: SharedPreferences,
    private val scope: () -> String
) {
    private val gson = Gson()

    /**
     * The card list is read through an explicit TypeToken, exactly as [RecentActivityStore] does.
     *
     * This is not a style choice. The first version stored a `Snapshot(cards, fetchedAt)` object and
     * let Gson learn the element type from the field's generic signature. That works in a debug
     * build and in every unit test, and fails in a release build: R8's full mode strips generic
     * signatures from classes it was not told to keep, so Gson fell back to `LinkedTreeMap` and the
     * home screen died with a ClassCastException the moment it drew a cached card. A TypeToken
     * carries the element type in the deserializer call itself, where nothing can shrink it away.
     */
    private val cardListType = object : TypeToken<MutableList<HomeCard>>() {}.type

    /** Cards as they were last loaded, and when that was. */
    data class Snapshot(val cards: List<HomeCard>, val fetchedAt: Long)

    fun read(slot: String): Snapshot? = try {
        val stored = preferences.getString(keyFor(slot), null)
        if (stored == null) {
            null
        } else {
            val cards: List<HomeCard> = gson.fromJson(stored, cardListType) ?: emptyList()
            // Belt and braces against the failure above ever returning in another shape: an entry
            // that did not deserialize into real cards is a miss, not something to hand to an
            // adapter that will cast it.
            if (cards.any { it !is HomeCard }) null
            else Snapshot(cards, preferences.getLong(timeKeyFor(slot), 0L))
        }
    } catch (_: Exception) {
        // A corrupt or half-written entry -- including one written by the version that stored a
        // Snapshot object here -- must never keep a screen from loading. The next successful load
        // overwrites it.
        null
    }

    fun write(slot: String, cards: List<HomeCard>) {
        preferences.edit {
            putString(keyFor(slot), gson.toJson(cards, cardListType))
            putLong(timeKeyFor(slot), System.currentTimeMillis())
        }
    }

    fun clear(slot: String) {
        preferences.edit {
            remove(keyFor(slot))
            remove(timeKeyFor(slot))
        }
    }

    private fun keyFor(slot: String): String = "${scope()}:$slot"

    private fun timeKeyFor(slot: String): String = "${keyFor(slot)}:at"
}
