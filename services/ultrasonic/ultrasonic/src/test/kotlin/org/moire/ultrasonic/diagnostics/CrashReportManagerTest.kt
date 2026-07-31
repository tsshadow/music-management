package org.moire.ultrasonic.diagnostics

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test

class CrashReportManagerTest {

    @Test
    fun `an explicit crash file always produces a report, regardless of shutdown state`() {
        val report = buildPendingReport(
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
            hasExplicitCrashFile = false,
            explicitCrashText = "",
            hadUnexpectedShutdown = false,
            ringBufferText = "some trailing log"
        )

        report.shouldBeNull()
    }
}
