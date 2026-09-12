/*
 * DownloadStateWire.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import nl.teunschriks.mumamobile.service.DownloadState

/**
 * Collapses [DownloadState]'s nine values onto the five the `platform.storage` contract knows.
 *
 * The web player draws one glyph per row, so it wants a coarse answer. Two distinctions are
 * dropped on purpose: `PINNED` is reported as `done` because a pinned file and a cached file are
 * both simply present as far as a list row is concerned, and `RETRYING` is reported as `running`
 * because a retry is still a download in progress -- calling it `failed` would make a row flicker
 * between two glyphs while the download is in fact recovering.
 */
fun downloadStateWire(state: DownloadState): String = when (state) {
    DownloadState.QUEUED -> "queued"
    DownloadState.DOWNLOADING, DownloadState.RETRYING -> "running"
    DownloadState.DONE, DownloadState.PINNED -> "done"
    DownloadState.FAILED, DownloadState.CANCELLED -> "failed"
    DownloadState.IDLE, DownloadState.UNKNOWN -> "none"
}
