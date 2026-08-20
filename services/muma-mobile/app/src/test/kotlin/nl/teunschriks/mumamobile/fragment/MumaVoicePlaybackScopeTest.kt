/*
 * MumaVoicePlaybackScopeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.android.scope.AndroidScopeComponent
import org.koin.core.error.NoDefinitionFoundException
import org.koin.dsl.koinApplication
import org.robolectric.RobolectricTestRunner

/**
 * @brief The voice screen has to take its player from the activity's scope.
 *
 * @details [MediaPlayerManager] is `scoped` to `NavigationActivity` and deliberately absent from
 * the root scope, because one queue belongs to one hosting activity. `getKoinScope()` decides which
 * scope a `by inject()` reads from purely by type: an `AndroidScopeComponent` -- which is what
 * `ScopeFragment` is -- gets its own scope, linked to the activity's; anything else gets the root
 * scope, where the player is not.
 *
 * A plain `Fragment` therefore compiles, navigates, and even resolves a spoken query, then throws
 * `NoDefinitionFoundException` the first time playback dereferences the lazy -- which is the only
 * moment the injection is actually performed. The screen looked healthy right up to the point it
 * had something to play.
 */
@RunWith(RobolectricTestRunner::class)
class MumaVoicePlaybackScopeTest {

    @Test
    fun `the player is deliberately absent from the root scope`() {
        val koin = koinApplication { modules(mediaPlayerModule) }.koin

        val missing = try {
            koin.get<MediaPlayerManager>()
            false
        } catch (_: NoDefinitionFoundException) {
            true
        }

        missing `should be equal to` true
    }

    @Test
    fun `the voice screen injects from a scope rather than from the root`() {
        AndroidScopeComponent::class.java
            .isAssignableFrom(MumaVoiceFragment::class.java) `should be equal to` true
    }
}
