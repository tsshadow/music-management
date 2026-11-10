/*
 * ServerAddress.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import java.net.URI
import java.net.URISyntaxException
import java.util.Locale
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.ServerHosts
import nl.teunschriks.mumamobile.util.Settings
import timber.log.Timber

/**
 * The address of the server the app talks to, as the listener typed it on the first-run screen
 * (issue #192, docs/designs/first-run-server/). The one reader and writer of
 * [Settings.serverUrl]: everything else asks [StaticServers.serverUrl].
 *
 * The MuMa API address is never stored. It is derived from this one, see
 * [StaticServers.mumaBaseUrlFor].
 */
object ServerAddress {

    /** The example host a build without `muma.serverUrl` compiles in; it is never a real server. */
    const val EXAMPLE_SERVER_URL = "https://music.example.org"

    /** Why [normalize] refused an input. [wire] is the word the bridge answers with. */
    enum class Refusal(val wire: String) {
        /** Empty, no host, user info, a query, a fragment or something that is no address. */
        INVALID("invalid"),

        /** A scheme other than `https`. The app sends no cleartext to a server (bug report 054). */
        INSECURE("insecure"),
    }

    /** What [normalize] made of an input. */
    sealed interface Result {
        /** A usable address: `https`, lower-case scheme and host, no trailing slash. */
        data class Ok(val url: String) : Result

        /** Not an address the app can use, and why. */
        data class Refused(val reason: Refusal) : Result
    }

    /**
     * The stored address, or null while none is set (a fresh install). Runs [migrate] first, so a
     * component that starts before the app -- the media session Android Auto starts without the
     * UI -- reads the same answer.
     */
    fun current(): String? {
        migrate()
        return Settings.serverUrl.takeIf { it.isNotBlank() }
    }

    @Volatile
    private var migrated = false

    /** Runs [ServerAddressMigration] once per process. Called from `UApp.onCreate` and [current]. */
    fun migrate() {
        if (migrated) return
        synchronized(this) {
            if (migrated) return
            if (ServerAddressMigration.run(ServerAddressMigration.SettingsStore)) {
                Timber.i("Stored the build's server address for an existing install")
            }
            migrated = true
        }
    }

    /** Lets the next [current] run the migration again; tests only. */
    internal fun resetMigrationForTests() {
        migrated = false
    }

    /**
     * Turns what the listener typed into the address the app stores. Pure.
     *
     * Trims the input, adds `https://` when no scheme is given, lower-cases scheme and host and
     * strips a trailing slash. A path stays, for a server behind a prefix such as
     * `https://example.org/lms`. Refuses an empty input, a scheme other than `https`, a missing
     * host, user info (`user:pass@host`), a query and a fragment.
     */
    fun normalize(input: String): Result {
        val trimmed = input.trim()
        if (trimmed.isEmpty() || trimmed.any { it.isWhitespace() }) return Result.Refused(Refusal.INVALID)
        val withScheme = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        val uri = try {
            URI(withScheme)
        } catch (_: URISyntaxException) {
            return Result.Refused(Refusal.INVALID)
        }
        val scheme = uri.scheme?.lowercase(Locale.ROOT)
        return when {
            scheme == null -> Result.Refused(Refusal.INVALID)
            scheme != "https" -> Result.Refused(if (scheme == "http") Refusal.INSECURE else Refusal.INVALID)
            uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null ->
                Result.Refused(Refusal.INVALID)
            else -> hostAndPath(uri)?.let { Result.Ok("https://$it") } ?: Result.Refused(Refusal.INVALID)
        }
    }

    /**
     * `host[:port][/path]` of [uri], host lower-cased and the trailing slash gone; null without a
     * host. [ServerHosts.hostOf] reads a host [URI] refuses, such as one with an underscore.
     */
    private fun hostAndPath(uri: URI): String? {
        val authority = uri.rawAuthority ?: return null
        val host = ServerHosts.hostOf("https://$authority")
        val looksLikeHost = host.contains('.') || host == "localhost" || host.startsWith("[")
        if (host.isEmpty() || !looksLikeHost) return null
        val port = if (uri.port >= 0) ":${uri.port}" else ""
        val path = (uri.rawPath ?: "").trimEnd('/')
        return "$host$port$path"
    }

    /**
     * Whether [a] and [b] are the same server: the same host, port and path, whatever the case or
     * a trailing slash. A change between two such spellings keeps the session.
     */
    fun sameServer(a: String, b: String): Boolean {
        val left = (normalize(a) as? Result.Ok)?.url ?: return false
        val right = (normalize(b) as? Result.Ok)?.url ?: return false
        return left == right
    }

    /**
     * Stores [url], which [normalize] must accept, and makes the app use it: the cached server is
     * dropped and the music service is rebuilt on the main thread, so the native client, the car
     * and downloads ask the new server from the next request on.
     *
     * @throws IllegalArgumentException when [normalize] refuses [url].
     */
    fun store(url: String, provider: ActiveServerProvider) {
        val normalized = normalize(url) as? Result.Ok ?: throw IllegalArgumentException("not a server address")
        Settings.serverUrl = normalized.url
        provider.serverChanged()
    }

    /** Whether [url] is the server this APK was built for, or a host on `muma.ownDomain`. */
    fun isBuildServer(url: String): Boolean = ServerHosts.isOwn(url, BuildConfig.MUMA_SERVER_URL, BuildConfig.MUMA_OWN_DOMAIN)

    /**
     * The address a fresh install suggests on the first-run screen: the build's own server, or
     * `""` for a build with the example default.
     */
    fun suggestion(buildServerUrl: String = BuildConfig.MUMA_SERVER_URL): String = if (buildServerUrl.isBlank() || ServerHosts.hostOf(buildServerUrl) == ServerHosts.hostOf(EXAMPLE_SERVER_URL)) {
        ""
    } else {
        buildServerUrl
    }
}
