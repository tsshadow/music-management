/*
 * MumaVoicePlaybackScopeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import io.mockk.mockk
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.CacheCleaner
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.android.scope.AndroidScopeComponent
import org.koin.core.Koin
import org.koin.dsl.koinApplication
import org.koin.dsl.module
import org.robolectric.RobolectricTestRunner

/** Stands in for a screen that owns a Koin scope, so the scope qualifier is a declared one. */
private class ScopedHost

/**
 * @brief Where the player lives, and who can reach it.
 *
 * @details [MediaPlayerManager] used to be `scoped` to `NavigationActivity` and deliberately absent
 * from the root scope. `getKoinScope()` decides which scope a `by inject()` reads from purely by
 * type: an `AndroidScopeComponent` -- which is what `ScopeFragment` is -- gets its own scope, linked
 * to the activity's; anything else gets the root scope, where the player was not. A plain
 * `Fragment`, a `BroadcastReceiver` or a root `single` therefore compiled, navigated, and threw
 * `NoDefinitionFoundException` the first time playback dereferenced the lazy -- the only moment the
 * injection is actually performed. This screen was written as a plain `Fragment` first and looked
 * healthy right up to the point it had something to play; the car mode wiring died the same way in
 * `docs/bug-reports/031-app-crashes-on-launch-while-connected-to-the-car.md`.
 *
 * Both are application-scoped `single`s now, so no caller can get this wrong. What is left to pin
 * is that it really is one shared instance: a second one would mean a second queue.
 */
@RunWith(RobolectricTestRunner::class)
class MumaVoicePlaybackScopeTest {

    /**
     * The lifecycle support's two leaf dependencies live in `applicationModule` and reach for an
     * Android context of their own. Stubbing them keeps this about the scoping and nothing else.
     */
    private fun container(): Koin = koinApplication {
        modules(
            mediaPlayerModule,
            module {
                single<ImageLoaderProvider> { mockk(relaxed = true) }
                single<CacheCleaner> { mockk(relaxed = true) }
                scope<ScopedHost> { }
            }
        )
    }.koin

    @Test
    fun `the player and its lifecycle support resolve from the root scope`() {
        val koin = container()

        (koin.get<MediaPlayerManager>() === koin.get<MediaPlayerManager>()) `should be equal to` true
        (
            koin.get<MediaPlayerLifecycleSupport>() === koin.get<MediaPlayerLifecycleSupport>()
            ) `should be equal to` true
    }

    @Test
    fun `a screen scope resolves the very same player as the root`() {
        val koin = container()

        val fromScope = koin.createScope<ScopedHost>("a-screen").get<MediaPlayerManager>()

        (fromScope === koin.get<MediaPlayerManager>()) `should be equal to` true
    }

    @Test
    fun `the voice screen still owns a scope linked to the root`() {
        AndroidScopeComponent::class.java
            .isAssignableFrom(MumaVoiceFragment::class.java) `should be equal to` true
    }
}
