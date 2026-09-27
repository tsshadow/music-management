/*
 * MumaSettingsChanges.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import timber.log.Timber

/*
 * Helpers for the per-key settings write (`PATCH /api/users/{id}/settings/{app_id}`, issue #39,
 * bug report 116). A caller describes only the keys it changes, as a JSON object; the server merges
 * them into the account's blob, so a key another device wrote in the meantime survives.
 */

/**
 * [changes] as a JSON object, for the `set` of a settings `PATCH`. Anything that is not a JSON
 * object is a programming error in the caller, not something to send: it throws.
 */
internal fun settingsChangesObject(changes: String): JsonObject = JsonParser.parseString(changes) as? JsonObject
    ?: throw IllegalArgumentException("Settings changes must be a JSON object")

/**
 * [blob] with every top-level key of [changes] replaced -- what the server does with a `PATCH`,
 * for the fallback against a server that does not have it yet. A missing, broken or non-object
 * [blob] counts as empty, the same as the server and the web player treat it.
 */
internal fun mergeSettingsChanges(blob: String?, changes: String): String {
    val root = blob?.let {
        try {
            JsonParser.parseString(it) as? JsonObject
        } catch (@Suppress("TooGenericExceptionCaught") e: Exception) {
            Timber.w(e, "Malformed MuMa settings blob, treating it as empty")
            null
        }
    } ?: JsonObject()
    for ((key, value) in settingsChangesObject(changes).entrySet()) root.add(key, value)
    return root.toString()
}
