package nl.teunschriks.mumamobile.util

import java.io.File
import nl.teunschriks.mumamobile.log.RingBufferLoggerTree
import org.amshove.kluent.shouldContain
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import timber.log.Timber

@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class UncaughtExceptionHandlerTest {

    private val reportFile = File(FileUtil.ultrasonicDirectory, UncaughtExceptionHandler.CRASH_REPORT_NAME)

    @Before
    fun setUp() {
        reportFile.delete()
        RingBufferLoggerTree.plantToTimberForest()
    }

    @After
    fun tearDown() {
        reportFile.delete()
    }

    @Test
    fun `writes stacktrace and ring buffer content to a single crash report file`() {
        Timber.i("marker log line before crash")
        val handler = UncaughtExceptionHandler(RuntimeEnvironment.getApplication())

        handler.uncaughtException(Thread.currentThread(), IllegalStateException("boom"))

        val content = reportFile.readText()
        content shouldContain "IllegalStateException"
        content shouldContain "boom"
        content shouldContain "marker log line before crash"
    }
}
