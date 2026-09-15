/*
 * AppUpdate.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import androidx.core.net.toUri
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * The update check the legacy `util/UpdateChecker.kt` used to run from the Kotlin home screen,
 * as pure functions the plugin can call and a unit test can hit without a network.
 *
 * apk-hoster groups builds by the filename prefix `scripts/publish.sh` uploads under, so a
 * debug build asks after the debug series and a release build after the release one --
 * a phone on the production series can never be offered a debug APK, and the other way round.
 * Older installs asked for the "ultrasonic" series; apk-hoster's `APK_ALIASES` points that at
 * `muma-mobile`, which is why the prefix here need not know about the rename.
 */
object AppUpdate {

    /** What the hoster's `/api/version` answered, reduced to the fields the web reads. */
    data class Latest(val versionCode: Int, val versionName: String, val url: String)

    /** The series a build belongs to; the hoster knows nothing else about it. */
    fun seriesOf(debug: Boolean): String = if (debug) "muma-mobile-debug" else "muma-mobile"

    /** `${host}/api/version?apk=<series>&user=<user>` -- exactly the query the legacy checker sent. */
    fun versionUrl(host: String, series: String, user: String): String = host.toUri().buildUpon()
        .appendEncodedPath("api/version")
        .appendQueryParameter("apk", series)
        .appendQueryParameter("user", user)
        .build()
        .toString()

    /**
     * Parses the hoster's answer. `versionCode` arrives as a string there; a body without one --
     * or with something that is not a number -- reads as version 0, which never counts as newer.
     */
    fun parseLatest(body: String): Latest {
        val json = JSONObject(body)
        return Latest(
            versionCode = json.optString("versionCode", "0").toIntOrNull() ?: 0,
            versionName = json.optString("versionName", ""),
            url = json.optString("url", "")
        )
    }

    /**
     * One GET, meant for an IO thread; throws on anything but a 2xx with a body, and the plugin
     * turns that throw into a rejected call. The password header is what the hoster gates the
     * version query on, the same one the upload uses.
     */
    fun fetchLatest(client: OkHttpClient, url: String, versionName: String, password: String): Latest {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "muma-mobile/$versionName")
            .header("X-Upload-Password", password)
            .build()
        client.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "apk-hoster answered ${response.code}" }
            val body = checkNotNull(response.body?.string()) { "apk-hoster answered without a body" }
            return parseLatest(body)
        }
    }

    /** Strictly newer by `versionCode`; a same-code build with another name is not an update. */
    fun isNewer(latest: Latest, currentVersionCode: Int): Boolean = latest.versionCode > currentVersionCode

    /**
     * The download link with the guest credentials the hoster expects on a browser download,
     * carried over from the legacy dialog's "Download" button. An empty url stays empty rather
     * than becoming `?u=guest&p=guest` on its own.
     */
    fun downloadUrl(url: String): String {
        if (url.isBlank()) return ""
        return url.toUri().buildUpon()
            .appendQueryParameter("u", "guest")
            .appendQueryParameter("p", "guest")
            .build()
            .toString()
    }
}
