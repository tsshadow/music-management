/*
 * MumaDiagnosticsPlugin.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import nl.teunschriks.mumamobile.diagnostics.CrashReportManager
import nl.teunschriks.mumamobile.diagnostics.WebActionLog
import nl.teunschriks.mumamobile.diagnostics.WebEnvironment
import nl.teunschriks.mumamobile.log.logAction
import org.json.JSONArray

/**
 * `platform.diagnostics` — what the user did, for a crash report.
 *
 * Implements the `PlatformDiagnostics` typedef of `services/frontend/src/lib/platform/index.js`.
 * Every action goes to two places: [WebActionLog], which is bounded and readable back so
 * `report()` can answer, and `logAction`, which puts the same line in the Timber ring buffer
 * where the native app's own actions already are. That is what makes a report read as one
 * sequence rather than as two logs that have to be interleaved by hand.
 *
 * | JS | here |
 * |---|---|
 * | `log(action, detail)` | `log({action, detail})` |
 * | `report()` | `report()` → `{entries: [{action, at, detail}]}`, oldest first, at most 50 |
 * | `clear()` | `clear()` |
 * | `identify({bundleVersion, userAgent})` | `identify({bundleVersion, userAgent})` → [WebEnvironment] |
 * | — | `send()`, which is `CrashReportManager.sendManualReport` |
 */
@CapacitorPlugin(name = "MumaDiagnostics")
class MumaDiagnosticsPlugin : Plugin() {

    @PluginMethod
    fun log(call: PluginCall) {
        val action = call.getString("action").orEmpty()
        val detail = call.getObject("detail")?.toString()?.takeIf { it != "{}" }
        WebActionLog.record(action, detail)
        logAction(action, "web" to true, "detail" to detail)
        call.resolve()
    }

    @PluginMethod
    fun report(call: PluginCall) {
        val entries = JSONArray()
        WebActionLog.entries().forEach { entry ->
            entries.put(
                JSObject()
                    .put("action", entry.action)
                    .put("at", entry.at)
                    .put("detail", entry.detail)
            )
        }
        call.resolve(JSObject().put("entries", entries))
    }

    @PluginMethod
    fun clear(call: PluginCall) {
        WebActionLog.clear()
        call.resolve()
    }

    /**
     * Tells [WebEnvironment] which UI, which frontend build and which WebView a report from now
     * on describes. Called once, from the web boot path -- see `identifyBundle` in
     * `services/frontend/src/lib/diagnosticsLog.js`.
     */
    @PluginMethod
    fun identify(call: PluginCall) {
        WebEnvironment.identify(
            bundleVersion = call.getString("bundleVersion"),
            userAgent = call.getString("userAgent")
        )
        call.resolve()
    }

    /**
     * Sends the log now, through the same path the Kotlin settings screen uses: the ring buffer
     * of this session and the previous one, the crash-report endpoint, and a copy in Downloads.
     * The web action log rides along -- `CrashReportManager` appends it.
     */
    @PluginMethod
    fun send(call: PluginCall) {
        val context = context
        if (context == null) {
            call.reject("no context")
            return
        }
        CrashReportManager.sendManualReport(context)
        call.resolve()
    }
}
