/*
 * FakeCredentialCipher.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import java.util.Base64

/**
 * A [CredentialCipher] for Robolectric, which has no Android Keystore. It is not encryption -- the
 * value is Base64 behind a generation tag -- but it keeps the plaintext out of the file, and it
 * models the two failures that matter: [invalidate] makes the key unusable (lock-screen change,
 * vendor wipe), and [loseKey] makes every sealed value fail to open (a restore onto another device).
 * [failEncrypt] simulates a Keystore that cannot encrypt at all.
 */
class FakeCredentialCipher : CredentialCipher {
    private var generation = 1
    private var invalidated = false

    /** Every encrypt fails, even after [resetKey]. */
    var failEncrypt = false

    /** How often [resetKey] was called. */
    var resets = 0
        private set

    /** The current key throws on use until [resetKey] replaces it. */
    fun invalidate() {
        invalidated = true
    }

    /** The key is replaced: what was sealed before no longer opens. */
    fun loseKey() {
        generation++
    }

    override fun encrypt(plain: String): String {
        if (failEncrypt || invalidated) throw CredentialStorageException("encrypt failed: fake")
        return "g$generation:" + Base64.getEncoder().encodeToString(plain.toByteArray())
    }

    override fun decrypt(sealed: String): String {
        if (invalidated) throw CredentialStorageException("decrypt failed: fake invalidated")
        val prefix = "g$generation:"
        if (!sealed.startsWith(prefix)) throw CredentialStorageException("decrypt failed: fake bad tag")
        return String(Base64.getDecoder().decode(sealed.removePrefix(prefix)))
    }

    override fun resetKey() {
        resets++
        invalidated = false
        generation++
    }
}
