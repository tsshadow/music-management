package nl.teunschriks.mumamobile.diagnostics

import org.amshove.kluent.shouldBeEmpty
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
import org.junit.Before
import org.junit.Test

/**
 * The web UI's action log: bounded, oldest first, and included in a crash report.
 *
 * The bound is the contract's ("at most the last 50"), and it is the point of the class: a screen
 * that logs in a loop must not be able to push the interesting lines out of a report.
 */
class WebActionLogTest {

    @Before
    fun clear() = WebActionLog.clear()

    @Test
    fun `entries come back oldest first`() {
        WebActionLog.record("a", at = 1)
        WebActionLog.record("b", at = 2)

        WebActionLog.entries().map { it.action } shouldBeEqualTo listOf("a", "b")
    }

    @Test
    fun `the log keeps the last fifty and drops the oldest`() {
        (1..WebActionLog.MAX_ENTRIES + 10).forEach { WebActionLog.record("action$it", at = it.toLong()) }

        val entries = WebActionLog.entries()
        entries.size shouldBeEqualTo WebActionLog.MAX_ENTRIES
        entries.first().action shouldBeEqualTo "action11"
        entries.last().action shouldBeEqualTo "action60"
    }

    @Test
    fun `a blank action is not an entry`() {
        WebActionLog.record("  ")
        WebActionLog.entries().shouldBeEmpty()
    }

    @Test
    fun `a blank detail is left out rather than stored as empty`() {
        WebActionLog.record("play", detail = "   ", at = 1)
        WebActionLog.entries().single().detail shouldBeEqualTo null
    }

    @Test
    fun `an empty log adds nothing to a report`() {
        WebActionLog.asReportText() shouldBeEqualTo ""
    }

    @Test
    fun `the report text carries the header, the action and the detail`() {
        WebActionLog.record("player.play", detail = """{"trackId":"42"}""", at = 1700000000000)

        val text = WebActionLog.asReportText()
        text shouldContain WebActionLog.REPORT_HEADER
        text shouldContain "player.play"
        text shouldContain """{"trackId":"42"}"""
        text shouldContain "1700000000000"
    }

    // ------------------------------------------------- and how a report uses it

    @Test
    fun `a report with no web actions is exactly the ring buffer it always was`() {
        withWebActionLog("ring buffer", "") shouldBeEqualTo "ring buffer"
    }

    @Test
    fun `the web actions are appended after the log, not in front of it`() {
        withWebActionLog("ring buffer", "web actions") shouldBeEqualTo "ring buffer\n\nweb actions"
    }

    @Test
    fun `a session with only web actions still reports them`() {
        withWebActionLog("", "web actions") shouldBeEqualTo "web actions"
    }

    @Test
    fun `a manual report carries the web actions`() {
        val report = buildManualReport("current", previousSessionText = "", webActionLogText = "web actions")
        report.ringBufferText shouldBeEqualTo "current\n\nweb actions"
    }

    /**
     * A clean kill during a session that happened to have the web UI open is not a crash. Judging
     * on the ring buffer alone is what keeps the action log from turning one into a report.
     */
    @Test
    fun `web actions alone do not make an unclean shutdown reportable`() {
        buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = false,
            explicitCrashText = "",
            hadUnexpectedShutdown = true,
            ringBufferText = "",
            webActionLogText = "web actions"
        ) shouldBeEqualTo null
    }

    @Test
    fun `a real crash report carries the web actions too`() {
        val report = buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = true,
            explicitCrashText = "boom",
            hadUnexpectedShutdown = false,
            ringBufferText = "ring buffer",
            webActionLogText = "web actions"
        )!!

        report.stacktraceText shouldBeEqualTo "boom"
        report.ringBufferText shouldBeEqualTo "ring buffer\n\nweb actions"
    }

    /**
     * A JS error is recorded the same way any other web action is -- `MumaDiagnosticsPlugin.log`
     * does not distinguish them (see `logError` in `services/frontend/src/lib/diagnosticsLog.js`)
     * -- so a report reads the two kinds of line in the order they happened rather than as two
     * separate sections.
     */
    @Test
    fun `an uncaught web error sits alongside the actions that led up to it`() {
        WebActionLog.record("navigate", detail = """{"view":"albums"}""", at = 1)
        WebActionLog.record("js.error", detail = """{"message":"boom","stack":"at foo (app.js:1)"}""", at = 2)

        val text = WebActionLog.asReportText()
        text shouldContain "navigate"
        text shouldContain "js.error"
        text shouldContain "boom"
        text shouldContain "at foo (app.js:1)"
        (text.indexOf("navigate") < text.indexOf("js.error")) shouldBeEqualTo true
    }

    @Test
    fun `a manual report carries a web error, marker and all`() {
        WebActionLog.record("js.error", detail = """{"message":"boom"}""", at = 1)

        val report = buildManualReport("current session", webActionLogText = WebActionLog.asReportText())

        report.stacktraceText shouldBeEqualTo CrashReportManager.MANUAL_REPORT_MARKER
        report.ringBufferText shouldContain "js.error"
        report.ringBufferText shouldContain "boom"
    }
}
