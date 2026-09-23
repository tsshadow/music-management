package nl.teunschriks.mumamobile.service

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * Which requested tracks never reach a [DownloadTask]. The filter this replaces kept every track:
 * its `false` answers were thrown away inside `let` blocks, so the cached upcoming tracks were
 * handed to a task on every playback change and logged "already exists" every two seconds.
 */
@RunWith(RobolectricTestRunner::class)
class DownloadStateOnDiskTest {

    @Test
    fun `a pinned file is not downloaded again`() {
        DownloadService.stateOnDisk(pinnedExists = true, completeExists = false, save = false) shouldBeEqualTo
            DownloadState.PINNED
    }

    @Test
    fun `a cached file is not downloaded again`() {
        DownloadService.stateOnDisk(pinnedExists = false, completeExists = true, save = false) shouldBeEqualTo
            DownloadState.DONE
    }

    @Test
    fun `a cached file asked to be kept still goes to the task that renames it`() {
        DownloadService.stateOnDisk(pinnedExists = false, completeExists = true, save = true) shouldBeEqualTo null
    }

    @Test
    fun `a missing file is downloaded`() {
        DownloadService.stateOnDisk(pinnedExists = false, completeExists = false, save = false) shouldBeEqualTo null
    }
}
