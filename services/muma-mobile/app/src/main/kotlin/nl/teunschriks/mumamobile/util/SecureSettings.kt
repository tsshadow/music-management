package nl.teunschriks.mumamobile.util

import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import nl.teunschriks.mumamobile.api.muma.MumaTokenStorage
import nl.teunschriks.mumamobile.app.UApp

object SecureSettings : MumaTokenStorage {
    private const val PREFS_FILE = "secure_settings"

    private val masterKey by lazy {
        MasterKey.Builder(UApp.applicationContext())
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
    }

    private val sharedPreferences by lazy {
        EncryptedSharedPreferences.create(
            UApp.applicationContext(),
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    override var mumaAccessToken: String?
        get() = sharedPreferences.getString("muma_access_token", null)
        set(value) = sharedPreferences.edit().putString("muma_access_token", value).apply()

    override var mumaRefreshToken: String?
        get() = sharedPreferences.getString("muma_refresh_token", null)
        set(value) = sharedPreferences.edit().putString("muma_refresh_token", value).apply()

    fun clear() {
        sharedPreferences.edit().clear().apply()
    }
}
