/*
 * ServerAddressMigration.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.ServerHosts
import nl.teunschriks.mumamobile.util.Settings

/**
 * Gives an install from before issue #192 the server address it used, so the update shows no
 * first-run screen and keeps the session (docs/designs/first-run-server/technical.md).
 *
 * Builds before #192 talked to the address compiled into the APK. An install that was used --
 * signed in, a name stored, or a server made active -- gets that address stored once. A fresh
 * install gets nothing and asks. The example default is never stored: an install built with it
 * could never reach a server, so it asks like a fresh one.
 *
 * Plain JVM behind [Store], so a unit test can drive it without Android. Idempotent: a stored
 * address is never replaced, so it runs on every start.
 */
object ServerAddressMigration {

    /** What the migration reads and writes; [SettingsStore] backs it. */
    interface Store {
        /** The stored address, `""` while none is set. */
        var serverUrl: String

        /** The explicit signed-in flag (issue #101). */
        val signedIn: Boolean

        /** The stored account name, `""` when none. */
        val userName: String

        /** The active server id; `-1` is Offline, what a fresh install has. */
        val activeServer: Int

        /** The address the APK was built with. */
        val buildServerUrl: String
    }

    /** [Store] over [Settings] and [BuildConfig]. */
    object SettingsStore : Store {
        override var serverUrl: String
            get() = Settings.serverUrl
            set(value) {
                Settings.serverUrl = value
            }
        override val signedIn: Boolean get() = Settings.signedIn
        override val userName: String get() = Settings.staticUserName
        override val activeServer: Int get() = Settings.activeServer
        override val buildServerUrl: String get() = BuildConfig.MUMA_SERVER_URL
    }

    /** Stores the build address for a used install without one. Returns whether it stored it. */
    fun run(store: Store): Boolean {
        if (store.serverUrl.isNotBlank()) return false
        val used = store.signedIn || store.userName.isNotEmpty() || store.activeServer != ActiveServerProvider.OFFLINE_DB_ID
        if (!used) return false
        val build = store.buildServerUrl
        if (ServerHosts.hostOf(build) == ServerHosts.hostOf(ServerAddress.EXAMPLE_SERVER_URL)) return false
        // An http:// build address never worked (the app refuses cleartext, bug report 054); such
        // an install asks like a fresh one.
        val normalized = (ServerAddress.normalize(build) as? ServerAddress.Result.Ok)?.url ?: return false
        store.serverUrl = normalized
        return true
    }
}
