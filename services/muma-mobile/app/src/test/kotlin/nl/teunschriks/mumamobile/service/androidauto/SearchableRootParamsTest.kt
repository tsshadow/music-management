/*
 * SearchableRootParamsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import android.os.Bundle
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaLibraryService
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Android Auto hides its own search affordance inside an app that does not claim to support
 * search, which left the host's global search box as the only way to reach the parser. The root
 * has to say so, and it cannot say so by echoing back the params the caller sent.
 *
 * Robolectric only because a Bundle is an Android class.
 */
@OptIn(UnstableApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class, manifest = Config.NONE)
class SearchableRootParamsTest {

    @Test
    fun `the root claims search support even when the caller sent no params`() {
        val params = searchableRootParams(null)

        params.extras.getBoolean(BROWSER_SEARCH_SUPPORTED) `should be equal to` true
    }

    @Test
    fun `what the caller sent survives`() {
        val incoming = MediaLibraryService.LibraryParams.Builder()
            .setExtras(Bundle().apply { putString("caller", "gearhead") })
            .build()

        val params = searchableRootParams(incoming)

        params.extras.getString("caller") `should be equal to` "gearhead"
        params.extras.getBoolean(BROWSER_SEARCH_SUPPORTED) `should be equal to` true
    }

    @Test
    fun `the root sets a list as the default layout for both kinds of child`() {
        // The per-level params decide the layout wherever MuMa builds the level itself. This is
        // the fallback for anything the car asks for that never reaches those -- notably the
        // root's own children, which are category entries without cover art.
        val params = searchableRootParams(null)

        params.extras.getInt(CONTENT_STYLE_BROWSABLE_HINT) `should be equal to` CONTENT_STYLE_LIST_ITEM
        params.extras.getInt(CONTENT_STYLE_PLAYABLE_HINT) `should be equal to` CONTENT_STYLE_LIST_ITEM
    }

    @Test
    fun `the flags the caller set are carried through`() {
        val incoming = MediaLibraryService.LibraryParams.Builder()
            .setRecent(true)
            .build()

        val params = searchableRootParams(incoming)

        params.isRecent `should be equal to` true
        params.isOffline `should be equal to` false
    }
}
