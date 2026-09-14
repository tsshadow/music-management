/*
 * CarModeSessionWiringTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.di

import nl.teunschriks.mumamobile.car.CarModeIntent
import nl.teunschriks.mumamobile.car.CarModeSession
import org.amshove.kluent.`should be equal to`
import org.junit.After
import org.junit.Test
import org.koin.core.context.startKoin
import org.koin.core.context.stopKoin

/**
 * Pins that arriving in the car is answered by a definition with nothing left to resolve.
 *
 * [CarModeSession] is a `single`, so its definition is resolved by the root scope no matter who
 * asks for it. While `MediaPlayerManager` lived only in `scope<NavigationActivity>`, a `get` for the
 * player from inside this definition therefore compiled, started and navigated, and threw the moment
 * the car was first reported -- which is the app disappearing on launch in the car. The player is
 * application-scoped now (see `MediaPlayerModule`), so that particular trap is gone, but the shape
 * pinned here is the right one regardless: this class resolves nothing and takes what it needs as an
 * argument, which is also what keeps it testable without a container.
 *
 * Only [CarModeSession] is resolved here, so the rest of the module, which does need an Android
 * context, is never instantiated. The player's own scoping is pinned by `MumaVoicePlaybackScopeTest`.
 */
class CarModeSessionWiringTest {

    @After
    fun tearDown() = stopKoin()

    @Test
    fun `arriving in the car is answered without an activity scope`() {
        val koin = startKoin { modules(appPermanentStorage) }.koin

        val session = koin.get<CarModeSession>()

        session.onPresenceChanged(true) { false } `should be equal to` CarModeIntent.Offer
    }
}
