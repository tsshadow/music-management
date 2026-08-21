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
    private val snapshotType = object : TypeToken<Snapshot>() {}.type

    /** Cards as they were last loaded, and when that was. */
    data class Snapshot(val cards: List<HomeCard>, val fetchedAt: Long)

    fun read(slot: String): Snapshot? = try {
        val stored = preferences.getString(keyFor(slot), null)
        if (stored == null) null else gson.fromJson<Snapshot>(stored, snapshotType)
    } catch (_: Exception) {
        // A corrupt or half-written entry must never be able to keep a screen from loading; the
        // next successful load overwrites it.
        null
    }

    fun write(slot: String, cards: List<HomeCard>) {
        val snapshot = Snapshot(cards, System.currentTimeMillis())
        preferences.edit { putString(keyFor(slot), gson.toJson(snapshot)) }
    }

    fun clear(slot: String) {
        preferences.edit { remove(keyFor(slot)) }
    }

    private fun keyFor(slot: String): String = "${scope()}:$slot"
}
