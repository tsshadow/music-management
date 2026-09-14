/*
 * WebEnvironment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.diagnostics

/**
 * What the web UI told us about itself, for a crash report's metadata header.
 *
 * `CrashReportManager` used to always describe the legacy Kotlin UI, because that was the only UI
 * there was. Now a report can be requested while the Capacitor shell's WebView is what is actually
 * on screen, and the header needs to say so rather than let the device/app-version lines quietly
 * pass for "the app the user was looking at" when they were looking at the web one instead.
 *
 * [identify] is called once, from [nl.teunschriks.mumamobile.capacitor.MumaDiagnosticsPlugin.identify],
 * itself called once from the web boot path (`identifyBundle` in
 * `services/frontend/src/lib/diagnosticsLog.js`). The legacy fragments never call it, which is
 * exactly what makes [uiVariant] "legacy" by default rather than a guess: nothing here can tell a
 * session that never opened the web UI apart from one that has not booted yet, so absence is read
 * as the former.
 */
object WebEnvironment {

    @Volatile
    private var bundleVersion: String? = null

    @Volatile
    private var userAgent: String? = null

    @Volatile
    private var identified: Boolean = false

    /**
     * @param bundleVersion the frontend build's own version -- a git commit short hash today (see
     *   `vite.config.js`'s `muma-bundle-version` plugin), null when the bundle carries none (a dev
     *   server, or a build from before this existed).
     * @param userAgent the WebView's own `navigator.userAgent`.
     */
    fun identify(bundleVersion: String?, userAgent: String?) {
        this.bundleVersion = bundleVersion?.takeIf { it.isNotBlank() }
        this.userAgent = userAgent?.takeIf { it.isNotBlank() }
        identified = true
    }

    /** "web" once the web UI has identified itself this process; "legacy" otherwise. */
    fun uiVariant(): String = if (identified) "web" else "legacy"

    fun bundleVersionOrNull(): String? = bundleVersion

    fun userAgentOrNull(): String? = userAgent

    /** Tests only, so one test's `identify` cannot leak into the next. */
    fun reset() {
        bundleVersion = null
        userAgent = null
        identified = false
    }
}

/**
 * The lines [WebEnvironment] contributes to a crash report's metadata header.
 *
 * A top-level function, like [withWebActionLog] in `CrashReportManager.kt`, so it is testable
 * without Robolectric or a live [WebEnvironment] -- the values travel in as plain arguments.
 *
 * @param uiVariant [WebEnvironment.uiVariant]'s answer.
 * @param bundleVersion [WebEnvironment.bundleVersionOrNull]'s answer.
 * @param userAgent [WebEnvironment.userAgentOrNull]'s answer.
 * @return one line per known fact, each ending in `\n`; a blank field is left out entirely rather
 *   than printed as "null" -- a legacy-UI report has none of the last two, and that should read as
 *   "not applicable", not as a missing answer.
 */
internal fun buildEnvironmentHeader(
    uiVariant: String,
    bundleVersion: String?,
    userAgent: String?
): String = buildString {
    append("UI: ")
    append(uiVariant)
    append('\n')
    if (!bundleVersion.isNullOrBlank()) {
        append("Frontend bundle: ")
        append(bundleVersion)
        append('\n')
    }
    if (!userAgent.isNullOrBlank()) {
        append("WebView UA: ")
        append(userAgent)
        append('\n')
    }
}
