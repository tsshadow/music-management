package org.moire.ultrasonic.home

import android.content.SharedPreferences
import org.amshove.kluent.`should be equal to`
import org.junit.Test

class RecentActivityStoreTest {

    private fun card(id: String, type: HomeCardType = HomeCardType.ALBUM) =
        HomeCard(type = type, itemId = id, title = "T$id")

    private fun store(
        separatePerMode: Boolean = true,
        preferences: SharedPreferences = FakePreferences()
    ) = RecentActivityStore(preferences, separatePerMode = { separatePerMode })

    @Test
    fun `records newest first`() {
        val store = store()
        store.record(card("1"), setsMode = false)
        store.record(card("2"), setsMode = false)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("2", "1")
    }

    @Test
    fun `re-recording moves an item to the front without duplicating it`() {
        val store = store()
        store.record(card("1"), setsMode = false)
        store.record(card("2"), setsMode = false)
        store.record(card("1"), setsMode = false)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("1", "2")
    }

    @Test
    fun `same id but different type are distinct entries`() {
        val store = store()
        store.record(card("1", HomeCardType.ALBUM), setsMode = false)
        store.record(card("1", HomeCardType.ARTIST), setsMode = false)

        store.recent(setsMode = false).size `should be equal to` 2
    }

    @Test
    fun `trims to the maximum retained size`() {
        val store = store()
        repeat(30) { store.record(card("$it"), setsMode = false) }

        store.recent(setsMode = false, limit = 100).size `should be equal to` RecentActivityStore.MAX_ENTRIES
    }

    @Test
    fun `recent returns at most the default limit`() {
        val store = store()
        repeat(12) { store.record(card("$it"), setsMode = false) }

        store.recent(setsMode = false).size `should be equal to` RecentActivityStore.DEFAULT_LIMIT
    }

    @Test
    fun `separate per mode keeps songs and livesets apart`() {
        val store = store(separatePerMode = true)
        store.record(card("song"), setsMode = false)
        store.record(card("set"), setsMode = true)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("song")
        store.recent(setsMode = true).map { it.itemId } `should be equal to` listOf("set")
    }

    @Test
    fun `shared mode puts everything in one list`() {
        val store = store(separatePerMode = false)
        store.record(card("song"), setsMode = false)
        store.record(card("set"), setsMode = true)

        store.recent(setsMode = false).map { it.itemId } `should be equal to` listOf("set", "song")
    }

    @Test
    fun `the whole card survives a round trip`() {
        val store = store()
        val original = HomeCard(
            type = HomeCardType.DYNAMIC_PLAYLIST,
            itemId = "t1",
            title = "Recent Hardstyle",
            subtitle = "Playlist",
            coverArtId = "cover",
            payload = """{"genre":["Hardstyle"]}"""
        )

        store.record(original, setsMode = false)

        store.recent(setsMode = false).first() `should be equal to` original
    }

    @Test
    fun `corrupt stored json yields an empty list instead of crashing`() {
        val preferences = FakePreferences()
        preferences.edit().putString("home_recent_songs", "{not json").apply()

        store(preferences = preferences).recent(setsMode = false) `should be equal to` emptyList()
    }
}

/** Minimal in-memory [SharedPreferences]; only the string operations the store uses are real. */
private class FakePreferences : SharedPreferences {
    private val values = mutableMapOf<String, String?>()

    override fun getString(key: String?, defValue: String?): String? = values[key] ?: defValue

    override fun edit(): SharedPreferences.Editor = FakeEditor(values)

    override fun getAll(): MutableMap<String, *> = values
    override fun getStringSet(key: String?, defValues: MutableSet<String>?) = defValues
    override fun getInt(key: String?, defValue: Int) = defValue
    override fun getLong(key: String?, defValue: Long) = defValue
    override fun getFloat(key: String?, defValue: Float) = defValue
    override fun getBoolean(key: String?, defValue: Boolean) = defValue
    override fun contains(key: String?) = values.containsKey(key)

    override fun registerOnSharedPreferenceChangeListener(
        listener: SharedPreferences.OnSharedPreferenceChangeListener?
    ) = Unit

    override fun unregisterOnSharedPreferenceChangeListener(
        listener: SharedPreferences.OnSharedPreferenceChangeListener?
    ) = Unit
}

private class FakeEditor(
    private val values: MutableMap<String, String?>
) : SharedPreferences.Editor {
    private val pending = mutableMapOf<String, String?>()

    override fun putString(key: String?, value: String?): SharedPreferences.Editor {
        if (key != null) pending[key] = value
        return this
    }

    override fun apply() {
        values.putAll(pending)
        pending.clear()
    }

    override fun commit(): Boolean {
        apply()
        return true
    }

    override fun remove(key: String?): SharedPreferences.Editor {
        if (key != null) values.remove(key)
        return this
    }

    override fun clear(): SharedPreferences.Editor {
        values.clear()
        return this
    }

    override fun putStringSet(key: String?, values: MutableSet<String>?) = this
    override fun putInt(key: String?, value: Int) = this
    override fun putLong(key: String?, value: Long) = this
    override fun putFloat(key: String?, value: Float) = this
    override fun putBoolean(key: String?, value: Boolean) = this
}
