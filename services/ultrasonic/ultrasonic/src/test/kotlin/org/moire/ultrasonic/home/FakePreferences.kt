package org.moire.ultrasonic.home

import android.content.SharedPreferences

/** Minimal in-memory [SharedPreferences]; only the string operations the store uses are real. */
class FakePreferences : SharedPreferences {
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
