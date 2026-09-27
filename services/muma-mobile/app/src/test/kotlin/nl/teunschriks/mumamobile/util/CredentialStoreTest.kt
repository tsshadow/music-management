/*
 * CredentialStoreTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.content.Context
import android.content.SharedPreferences
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotContain
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * [CredentialStore] over real (Robolectric) preferences and [FakeCredentialCipher]: what reaches
 * the file, and what a key that stopped working does (issue #115).
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class CredentialStoreTest {

    private lateinit var prefs: SharedPreferences
    private val cipher = FakeCredentialCipher()
    private var unreadable = 0
    private lateinit var store: CredentialStore

    @Before
    fun setUp() {
        prefs = RuntimeEnvironment.getApplication().getSharedPreferences("credential_store_test", Context.MODE_PRIVATE)
        prefs.edit().clear().commit()
        store = CredentialStore({ prefs }, cipher) { unreadable++ }
    }

    /** A second store over the same file, as the next process start would open it. */
    private fun reopened() = CredentialStore({ prefs }, cipher) { unreadable++ }

    @Test
    fun `a stored value reads back, also after a restart, and only ciphertext is on disk`() {
        store.put("muma_api_key", "444e005e") shouldBeEqualTo true

        store.get("muma_api_key") shouldBeEqualTo "444e005e"
        reopened().get("muma_api_key") shouldBeEqualTo "444e005e"
        prefs.all.values.joinToString() shouldNotContain "444e005e"
    }

    @Test
    fun `an empty value removes the entry`() {
        store.put("muma_api_key", "444e005e")

        store.put("muma_api_key", "")

        store.get("muma_api_key").shouldBeNull()
        prefs.contains("muma_api_key") shouldBeEqualTo false
    }

    @Test
    fun `clear removes everything`() {
        store.put("muma_api_key", "a")
        store.put("subsonic_token", "b")

        store.clear()

        prefs.all.isEmpty() shouldBeEqualTo true
        store.get("muma_api_key").shouldBeNull()
    }

    @Test
    fun `an invalidated key drops every value, resets the key and reports it once`() {
        store.put("muma_api_key", "a")
        store.put("subsonic_token", "b")
        cipher.invalidate()

        val fresh = reopened()
        fresh.get("muma_api_key").shouldBeNull()
        fresh.get("subsonic_token").shouldBeNull()

        unreadable shouldBeEqualTo 1
        cipher.resets shouldBeEqualTo 1
        prefs.all.isEmpty() shouldBeEqualTo true
    }

    @Test
    fun `ciphertext restored without its key reads as nothing`() {
        store.put("muma_api_key", "a")
        cipher.loseKey()

        reopened().get("muma_api_key").shouldBeNull()

        unreadable shouldBeEqualTo 1
        prefs.all.isEmpty() shouldBeEqualTo true
    }

    @Test
    fun `a write under an invalidated key succeeds with a fresh key`() {
        store.put("subsonic_token", "old")
        cipher.invalidate()

        store.put("muma_api_key", "new") shouldBeEqualTo true

        reopened().get("muma_api_key") shouldBeEqualTo "new"
        // The values under the old key are gone with it; a write does not sign out by itself.
        reopened().get("subsonic_token").shouldBeNull()
        unreadable shouldBeEqualTo 0
    }

    @Test
    fun `a keystore that cannot encrypt stores nothing and says so`() {
        cipher.failEncrypt = true

        store.put("muma_api_key", "a") shouldBeEqualTo false

        prefs.all.isEmpty() shouldBeEqualTo true
        store.get("muma_api_key").shouldBeNull()
    }
}
