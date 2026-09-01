package nl.teunschriks.mumamobile.wizard

import android.content.Context
import androidx.core.content.edit
import androidx.preference.PreferenceManager

/**
 * The wizard's read/write seam.
 *
 * Settings/SettingsDelegate resolve their store through a `by lazy` on UApp.applicationContext(),
 * which pins them to the first application instance in the classloader - a test can write through
 * them but never observe the result. This interface exists so the controls can be driven by a
 * fake, while production still talks to the exact store androidx.preference uses.
 */
interface WizardPreferences {
    fun getBoolean(key: String, default: Boolean): Boolean
    fun putBoolean(key: String, value: Boolean)
    fun getString(key: String, default: String): String
    fun putString(key: String, value: String)
}

class SharedWizardPreferences(context: Context) : WizardPreferences {
    private val store = PreferenceManager.getDefaultSharedPreferences(context)

    override fun getBoolean(key: String, default: Boolean): Boolean = store.getBoolean(key, default)

    override fun putBoolean(key: String, value: Boolean) = store.edit { putBoolean(key, value) }

    override fun getString(key: String, default: String): String = store.getString(key, default) ?: default

    override fun putString(key: String, value: String) = store.edit { putString(key, value) }
}
