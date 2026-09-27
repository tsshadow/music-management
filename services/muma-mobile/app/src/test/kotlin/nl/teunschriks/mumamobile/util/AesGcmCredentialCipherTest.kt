/*
 * AesGcmCredentialCipherTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldNotBeEqualTo
import org.amshove.kluent.shouldNotContain
import org.junit.Test

/**
 * The AES-GCM framing of issue #115 over a software key, since the JVM has no Android Keystore:
 * the same cipher code runs in the app, only [CredentialKeySource] differs.
 */
class AesGcmCredentialCipherTest {

    /** A key source holding an ordinary JCE AES key in memory. */
    private class MemoryKeySource : CredentialKeySource {
        var key: SecretKey? = null

        override fun existingKey(): SecretKey? = key

        override fun getOrCreateKey(): SecretKey = key ?: KeyGenerator.getInstance("AES").apply { init(256) }.generateKey().also { key = it }

        override fun deleteKey() {
            key = null
        }
    }

    private val keys = MemoryKeySource()
    private val cipher = AesGcmCredentialCipher(keys)

    private fun failsToOpen(sealed: String): Boolean = try {
        cipher.decrypt(sealed)
        false
    } catch (e: CredentialStorageException) {
        true
    }

    @Test
    fun `a value round-trips and is not in the sealed form`() {
        val sealed = cipher.encrypt("444e005eefa57d15")

        sealed shouldNotContain "444e005eefa57d15"
        cipher.decrypt(sealed) shouldBeEqualTo "444e005eefa57d15"
    }

    @Test
    fun `every encryption uses a fresh iv`() {
        cipher.encrypt("same") shouldNotBeEqualTo cipher.encrypt("same")
    }

    @Test
    fun `a tampered value does not open`() {
        val sealed = cipher.encrypt("key")
        val parts = sealed.split(':')
        val body = java.util.Base64.getDecoder().decode(parts[2])
        body[0] = (body[0].toInt() xor 1).toByte()
        val tampered = "${parts[0]}:${parts[1]}:${java.util.Base64.getEncoder().encodeToString(body)}"

        failsToOpen(tampered) shouldBeEqualTo true
    }

    @Test
    fun `a value sealed under a key that was replaced does not open`() {
        val sealed = cipher.encrypt("key")
        cipher.resetKey()
        cipher.encrypt("new key")

        failsToOpen(sealed) shouldBeEqualTo true
    }

    @Test
    fun `without a key -- a restore onto another device -- nothing opens`() {
        val sealed = cipher.encrypt("key")
        keys.key = null

        failsToOpen(sealed) shouldBeEqualTo true
    }

    @Test
    fun `anything not written by the cipher does not open`() {
        failsToOpen("plain-api-key") shouldBeEqualTo true
        failsToOpen("v1:not base64:!!") shouldBeEqualTo true
    }

    @Test
    fun `a key source that throws becomes a storage exception`() {
        val broken = AesGcmCredentialCipher(object : CredentialKeySource {
            override fun existingKey(): SecretKey? = throw java.security.KeyStoreException("gone")
            override fun getOrCreateKey(): SecretKey = throw java.security.ProviderException("keystore daemon")
            override fun deleteKey() = throw java.security.KeyStoreException("gone")
        })

        val encryptFailed = try {
            broken.encrypt("key")
            false
        } catch (e: CredentialStorageException) {
            true
        }
        encryptFailed shouldBeEqualTo true
        broken.resetKey() // never throws
    }
}
