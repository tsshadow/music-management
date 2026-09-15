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

    @Test
    fun `the version url is the legacy checker's query`() {
        AppUpdate.versionUrl("https://apk.example", "muma-mobile-debug", "muma-mobile") shouldBeEqualTo
            "https://apk.example/api/version?apk=muma-mobile-debug&user=muma-mobile"
    }

    @Test
    fun `the hoster's string versionCode is compared as a number`() {
        val latest = AppUpdate.parseLatest("""{"versionCode":"313","versionName":"6.36.0","url":"https://apk.example/dl/313"}""")
        latest.versionCode shouldBeEqualTo 313
        latest.versionName shouldBeEqualTo "6.36.0"
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
