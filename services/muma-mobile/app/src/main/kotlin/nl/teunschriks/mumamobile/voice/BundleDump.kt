/*
 * BundleDump.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.voice

import android.os.Bundle
import timber.log.Timber

/**
 * Writes every key of an extras bundle into a [QueryTrace].
 *
 * Assistant hands MuMa a rewritten utterance and puts what it understood into the extras instead:
 * it strips the word "genre" precisely when it read the request as a genre one, and sets
 * `EXTRA_MEDIA_GENRE`. Exactly one key of that bundle has ever been read, because somebody guessed
 * it would be there. `EXTRA_MEDIA_ARTIST`, `EXTRA_MEDIA_ALBUM`, `EXTRA_MEDIA_TITLE`,
 * `EXTRA_MEDIA_PLAYLIST`, `EXTRA_MEDIA_FOCUS` and whatever else Assistant sends have never been
 * looked at. Reading the whole bundle is what turns a guess into evidence.
 *
 * Nothing here may throw. An extras bundle arrives from another process and can fail to unparcel,
 * and a diagnostic that takes the request down with it is worse than no diagnostic.
 */
fun Bundle?.dumpInto(trace: QueryTrace, prefix: String = "") {
    if (this == null) {
        if (prefix.isEmpty()) trace.extra("(none)", "no extras")
        return
    }

    runCatching {
        val keys = keySet()
        if (keys.isEmpty()) {
            if (prefix.isEmpty()) trace.extra("(none)", "no extras")
            return@runCatching
        }

        keys.forEach { key ->
            val name = if (prefix.isEmpty()) key else "$prefix.$key"
            @Suppress("DEPRECATION")
            when (val value = get(key)) {
                is Bundle -> value.dumpInto(trace, name)
                null -> trace.extra(name, "null")
                else -> trace.extra(name, value.toString())
            }
        }
    }.onFailure {
        Timber.w(it, "could not read the extras bundle")
        trace.extra("(unreadable)", it.javaClass.simpleName)
    }
}
