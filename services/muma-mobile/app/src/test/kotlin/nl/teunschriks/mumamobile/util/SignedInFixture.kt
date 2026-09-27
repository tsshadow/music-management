/*
 * SignedInFixture.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

/**
 * Puts a Robolectric test in the state of a signed-in phone that already holds its Subsonic token,
 * so the car's token gate ([nl.teunschriks.mumamobile.service.androidauto.SubsonicAccess]) lets a
 * browse through without fetching anything.
 *
 * Browse tests used to pass that gate by accident: the old `EncryptedSharedPreferences` threw on
 * Robolectric, which has no Keystore, and the gate lets a request through when its check throws.
 * The encrypted store of issue #115 handles a missing Keystore as "no credentials" instead, so the
 * tests now say what state they need, with a [FakeCredentialCipher] standing in for the Keystore.
 */
object SignedInFixture {
    const val USER = "user"

    /** Signed in as [USER], with a MuMa key and a Subsonic token issued for that name. */
    fun install() {
        SecureSettings.useCipherForTests(FakeCredentialCipher())
        Settings.staticUserName = USER
        Settings.signedIn = true
        SecureSettings.mumaApiKey = "fixture-api-key"
        SecureSettings.subsonicToken = "fixture-subsonic-token"
        SecureSettings.subsonicTokenUser = USER
    }
}
