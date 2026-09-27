/*
 * CredentialCipher.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.KeyStore
import java.security.ProviderException
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import timber.log.Timber

/**
 * Seals and opens one credential value for [CredentialStore] (issue #115).
 *
 * An interface so a Robolectric test can put a fake behind [SecureSettings]: Robolectric has no
 * Android Keystore, and what those tests check is the store's behaviour -- migration, a key that
 * went away -- not the encryption itself.
 */
interface CredentialCipher {
    /** Encrypts [plain]; throws [CredentialStorageException] when no key can be had. */
    fun encrypt(plain: String): String

    /**
     * Decrypts what [encrypt] returned; throws [CredentialStorageException] when the key is gone,
     * was replaced or invalidated, or [sealed] was not written with it.
     */
    fun decrypt(sealed: String): String

    /** Drops the key, so the next [encrypt] starts with a fresh one. Never throws. */
    fun resetKey()
}

/** The credential could not be encrypted or decrypted; see [CredentialCipher]. */
class CredentialStorageException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** Where [AesGcmCredentialCipher] gets its AES key; the Android Keystore in the app. */
interface CredentialKeySource {
    /** The key, or null when none exists (a fresh install, or a restore to another device). */
    fun existingKey(): SecretKey?

    /** The key, created when none exists yet. */
    fun getOrCreateKey(): SecretKey

    /** Deletes the key; a no-op when there is none. */
    fun deleteKey()
}

/**
 * AES-256-GCM over a key from [keys]. The sealed form is `v1:<base64 iv>:<base64 ciphertext+tag>`;
 * GCM's tag means a value encrypted under another key, or tampered with, fails to open rather than
 * decrypting to garbage.
 */
class AesGcmCredentialCipher(private val keys: CredentialKeySource) : CredentialCipher {

    override fun encrypt(plain: String): String = guard("encrypt") {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        // No IV passed in: the Keystore requires it to pick a random one itself.
        cipher.init(Cipher.ENCRYPT_MODE, keys.getOrCreateKey())
        val sealed = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        val encoder = Base64.getEncoder()
        "$VERSION:${encoder.encodeToString(cipher.iv)}:${encoder.encodeToString(sealed)}"
    }

    override fun decrypt(sealed: String): String = guard("decrypt") {
        val parts = sealed.split(':')
        if (parts.size != 3 || parts[0] != VERSION) throw CredentialStorageException("unknown format")
        val key = keys.existingKey() ?: throw CredentialStorageException("no key")
        val decoder = Base64.getDecoder()
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, decoder.decode(parts[1])))
        String(cipher.doFinal(decoder.decode(parts[2])), Charsets.UTF_8)
    }

    override fun resetKey() {
        try {
            keys.deleteKey()
        } catch (e: GeneralSecurityException) {
            // The next encrypt tries again and fails loudly if the Keystore is gone.
            Timber.w("Could not delete the credential key: %s", e.javaClass.simpleName)
        } catch (e: ProviderException) {
            Timber.w("Could not delete the credential key: %s", e.javaClass.simpleName)
        } catch (e: IOException) {
            Timber.w("Could not delete the credential key: %s", e.javaClass.simpleName)
        }
    }

    /**
     * Turns every way the JCA and the Keystore fail -- KeyPermanentlyInvalidatedException,
     * AEADBadTagException, UnrecoverableKeyException, a ProviderException from the Keystore
     * daemon, bad Base64 -- into the one exception [CredentialStore] handles.
     */
    private inline fun <T> guard(what: String, block: () -> T): T = try {
        block()
    } catch (e: CredentialStorageException) {
        throw e
    } catch (e: GeneralSecurityException) {
        throw CredentialStorageException("$what failed: ${e.javaClass.simpleName}", e)
    } catch (e: ProviderException) {
        throw CredentialStorageException("$what failed: ${e.javaClass.simpleName}", e)
    } catch (e: IllegalArgumentException) {
        throw CredentialStorageException("$what failed: ${e.javaClass.simpleName}", e)
    } catch (e: IllegalStateException) {
        throw CredentialStorageException("$what failed: ${e.javaClass.simpleName}", e)
    } catch (e: IOException) {
        throw CredentialStorageException("$what failed: ${e.javaClass.simpleName}", e)
    }

    private companion object {
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_BITS = 128
        const val VERSION = "v1"
    }
}

/**
 * An AES-256 key in the Android Keystore: generated and kept by the Keystore (hardware-backed where
 * the device has it), never readable by the app, and not part of any backup.
 *
 * No user authentication is required to use it, on purpose: Android Auto starts the media session
 * while the phone is locked in the car, and it has to read the MuMa key then. That also means a
 * lock-screen change does not invalidate it; when the Keystore loses it anyway (some vendors, a
 * restore to another device), [CredentialStore] treats the credentials as gone.
 */
class KeystoreCredentialKeySource(private val alias: String = ALIAS) : CredentialKeySource {

    private fun keyStore(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    override fun existingKey(): SecretKey? = keyStore().getKey(alias, null) as? SecretKey

    override fun getOrCreateKey(): SecretKey = existingKey() ?: synchronized(this) {
        existingKey() ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER).run {
            init(
                KeyGenParameterSpec.Builder(
                    alias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(KEY_BITS)
                    .setRandomizedEncryptionRequired(true)
                    .build()
            )
            generateKey()
        }
    }

    override fun deleteKey() {
        val store = keyStore()
        if (store.containsAlias(alias)) store.deleteEntry(alias)
    }

    companion object {
        const val PROVIDER = "AndroidKeyStore"
        const val ALIAS = "muma_credentials_aes_v1"
        private const val KEY_BITS = 256
    }
}
