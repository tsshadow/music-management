/*
 * AppUpdateTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Robolectric for `android.net.Uri`; the stub jar's `Uri.parse` answers null. */
@RunWith(RobolectricTestRunner::class)
class AppUpdateTest {

    @Test
    fun `a debug build asks after the debug series and a release build after the release one`() {
        AppUpdate.seriesOf(debug = true) shouldBeEqualTo "muma-mobile-debug"
        AppUpdate.seriesOf(debug = false) shouldBeEqualTo "muma-mobile"
    }

    /** A release phone must never hear about a debug APK; a debug phone must hear about a release. */
    @Test
    fun `a release build asks its own series only, a debug build its own and then the release one`() {
        AppUpdate.seriesToAsk(debug = false) shouldBeEqualTo listOf("muma-mobile")
        AppUpdate.seriesToAsk(debug = true) shouldBeEqualTo listOf("muma-mobile-debug", "muma-mobile")
    }

    /** The debug series stuck at 316 while releases went to 320: the release answer is the one that counts. */
    @Test
    fun `the newest answer wins across series, and a tie keeps the own series`() {
        val debug = AppUpdate.Latest(316, "7.0.0", "https://apk.example/dl/316", "muma-mobile-debug")
        val release = AppUpdate.Latest(320, "7.3.0", "https://apk.example/dl/320", "muma-mobile")
        AppUpdate.newest(listOf(debug, release)) shouldBeEqualTo release
        AppUpdate.newest(listOf(debug, release.copy(versionCode = 316))) shouldBeEqualTo debug
        AppUpdate.newest(emptyList()) shouldBeEqualTo null
    }

    /** The query used to send the hoster's upload password; the read-only guest is enough (bug report 054). */
    @Test
    fun `the version url asks as the read-only guest`() {
        AppUpdate.versionUrl("https://apk.example", "muma-mobile-debug") shouldBeEqualTo
            "https://apk.example/api/version?apk=muma-mobile-debug&u=guest&p=guest"
    }

    @Test
    fun `the hoster's string versionCode is compared as a number`() {
        val latest = AppUpdate.parseLatest(
            """{"versionCode":"313","versionName":"6.36.0","url":"https://apk.example/dl/313"}""",
            "muma-mobile"
        )
        latest.versionCode shouldBeEqualTo 313
        latest.versionName shouldBeEqualTo "6.36.0"
        latest.series shouldBeEqualTo "muma-mobile"
        AppUpdate.isNewer(latest, currentVersionCode = 312) shouldBeEqualTo true
        AppUpdate.isNewer(latest, currentVersionCode = 313) shouldBeEqualTo false
        AppUpdate.isNewer(latest, currentVersionCode = 314) shouldBeEqualTo false
    }

    /** A body without a code, or with garbage in it, must never look like an update. */
    @Test
    fun `a missing or unreadable versionCode is never newer`() {
        AppUpdate.isNewer(AppUpdate.parseLatest("""{"versionName":"x"}"""), 0) shouldBeEqualTo false
        AppUpdate.isNewer(AppUpdate.parseLatest("""{"versionCode":"soon"}"""), 0) shouldBeEqualTo false
    }

    @Test
    fun `the download link carries the guest credentials, an empty one stays empty`() {
        AppUpdate.downloadUrl("https://apk.example/dl/313") shouldBeEqualTo "https://apk.example/dl/313?u=guest&p=guest"
        AppUpdate.downloadUrl("") shouldBeEqualTo ""
    }
}
