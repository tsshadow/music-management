package nl.teunschriks.mumamobile.diagnostics

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldContain
import org.junit.Test

class CrashReportManagerTest {

    @Test
    fun `an explicit crash file always produces a report, regardless of shutdown state`() {
        val report = buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = true,
            explicitCrashText = "java.lang.IllegalStateException: boom",
            hadUnexpectedShutdown = false,
            ringBufferText = "log line"
        )

        report!!.stacktraceText shouldBeEqualTo "java.lang.IllegalStateException: boom"
        report.ringBufferText shouldBeEqualTo "log line"
    }

    @Test
    fun `an unexpected shutdown with ring buffer content produces an implicit report`() {
        val report = buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = false,
            explicitCrashText = "",
            hadUnexpectedShutdown = true,
            ringBufferText = "last line before kill"
        )

        report!!.stacktraceText.shouldBeNull()
        report.ringBufferText shouldBeEqualTo "last line before kill"
    }

    @Test
    fun `an unexpected shutdown with an empty ring buffer produces no report`() {
        val report = buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = false,
            explicitCrashText = "",
            hadUnexpectedShutdown = true,
            ringBufferText = "   "
        )

        report.shouldBeNull()
    }

    @Test
    fun `a clean shutdown with no crash file produces no report`() {
        val report = buildPendingReport(
            crashDetectionEnabled = true,
            hasExplicitCrashFile = false,
            explicitCrashText = "",
            hadUnexpectedShutdown = false,
            ringBufferText = "some trailing log"
        )

        report.shouldBeNull()
    }

    @Test
    fun `no report is produced when crash detection is disabled, even after a real crash`() {
        val report = buildPendingReport(
            crashDetectionEnabled = false,
            hasExplicitCrashFile = true,
            explicitCrashText = "java.lang.IllegalStateException: boom",
            hadUnexpectedShutdown = true,
            ringBufferText = "last line before kill"
        )

        report.shouldBeNull()
    }

    @Test
    fun `a manual report is marked as manual and carries the current ring buffer`() {
        val report = buildManualReport(currentSessionText = "what happened just now")

        report.stacktraceText shouldBeEqualTo CrashReportManager.MANUAL_REPORT_MARKER
        report.ringBufferText shouldBeEqualTo "what happened just now"
    }

    @Test
    fun `a manual report is produced even with an empty ring buffer`() {
        val report = buildManualReport(currentSessionText = "")

        report.stacktraceText shouldBeEqualTo CrashReportManager.MANUAL_REPORT_MARKER
        report.ringBufferText shouldBeEqualTo ""
    }

    @Test
    fun `the text of a manual report contains both the marker and the log`() {
        val text = buildManualReport(currentSessionText = "log line").toReportText()

        text shouldContain CrashReportManager.MANUAL_REPORT_MARKER
        text shouldContain "log line"
    }

    @Test
    fun `a manual report carries the previous session's log before the current one`() {
        val report = buildManualReport(
            currentSessionText = "line from after the restart",
            previousSessionText = "line from the screen that hung"
        )

        report.ringBufferText shouldContain CrashReportManager.PREVIOUS_SESSION_HEADER
        report.ringBufferText shouldContain "line from the screen that hung"
        report.ringBufferText shouldContain CrashReportManager.CURRENT_SESSION_HEADER
        report.ringBufferText shouldContain "line from after the restart"

        val previousAt = report.ringBufferText.indexOf("line from the screen that hung")
        val currentAt = report.ringBufferText.indexOf("line from after the restart")
        (previousAt < currentAt) shouldBeEqualTo true
    }

    @Test
    fun `a blank previous session leaves the manual report exactly as it was`() {
        val report = buildManualReport(
            currentSessionText = "only this session",
            previousSessionText = "   "
        )

        report.ringBufferText shouldBeEqualTo "only this session"
    }
}
