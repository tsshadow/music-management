/*
 * CredentialMigrationTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/** [CredentialMigration] against an in-memory [CredentialMigration.Store] (issue #115). */
class CredentialMigrationTest {

    private class MemoryStore(
        override var plainApiKey: String = "",
        var encrypted: String = "",
        var legacyFile: Boolean = false,
        override var signedIn: Boolean = true,
        val keystoreWorks: Boolean = true
    ) : CredentialMigration.Store {
        override fun clearPlainApiKey() {
            plainApiKey = ""
        }

        override fun storeEncryptedApiKey(key: String): Boolean {
            if (!keystoreWorks) return false
            encrypted = key
            return true
        }

        override fun legacyEncryptedFileExists() = legacyFile

        override fun deleteLegacyEncryptedFile() {
            legacyFile = false
        }
    }

    @Test
    fun `the plain key moves into the encrypted store and the plain copy is removed`() {
        val store = MemoryStore(plainApiKey = "key-1")

        CredentialMigration.run(store) shouldBeEqualTo true

        store.encrypted shouldBeEqualTo "key-1"
        store.plainApiKey shouldBeEqualTo ""
        store.signedIn shouldBeEqualTo true
    }

    @Test
    fun `a second run changes nothing`() {
        val store = MemoryStore(plainApiKey = "key-1", legacyFile = true)
        CredentialMigration.run(store)

        CredentialMigration.run(store) shouldBeEqualTo false

        store.encrypted shouldBeEqualTo "key-1"
    }

    @Test
    fun `an install without a plain key or old file is left alone`() {
        val store = MemoryStore(encrypted = "key-2")

        CredentialMigration.run(store) shouldBeEqualTo false

        store.encrypted shouldBeEqualTo "key-2"
        store.signedIn shouldBeEqualTo true
    }

    @Test
    fun `a keystore that cannot encrypt still removes the plain copy and signs out`() {
        val store = MemoryStore(plainApiKey = "key-1", keystoreWorks = false)

        CredentialMigration.run(store) shouldBeEqualTo true

        store.plainApiKey shouldBeEqualTo ""
        store.encrypted shouldBeEqualTo ""
        store.signedIn shouldBeEqualTo false
    }

    @Test
    fun `the old encrypted file is deleted`() {
        val store = MemoryStore(legacyFile = true)

        CredentialMigration.run(store) shouldBeEqualTo true

        store.legacyFile shouldBeEqualTo false
    }
}
