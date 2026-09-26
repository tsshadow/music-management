package nl.teunschriks.mumamobile.util

import androidx.core.content.edit
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

    /**
     * The signed-in user's Subsonic API token (`GET /api/auth/subsonic-token`), which every `/rest`
     * call is signed with as `t=md5(token + salt)&s=salt`. Kept here, encrypted, next to the MuMa
     * tokens rather than in the plain preferences, and cleared with them on sign-out.
     */
    var subsonicToken: String?
        get() = sharedPreferences.getString("subsonic_token", null)
        set(value) = sharedPreferences.edit { putString("subsonic_token", value) }

    /** The LMS login name [subsonicToken] was issued for; the token signs for that name only. */
    var subsonicTokenUser: String?
        get() = sharedPreferences.getString("subsonic_token_user", null)
        set(value) = sharedPreferences.edit { putString("subsonic_token_user", value) }

    fun clear() {
        sharedPreferences.edit().clear().apply()
    }
}
