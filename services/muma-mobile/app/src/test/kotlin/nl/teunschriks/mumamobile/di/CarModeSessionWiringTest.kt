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
 * Pins that arriving in the car can be answered from the root scope.
 *
 * [CarModeSession] is a `single`, so its definition is resolved by the root scope no matter who
 * asks for it, while `MediaPlayerManager` only exists inside `scope<NavigationActivity>`. A `get`
 * for the player from inside this definition therefore compiles, starts and navigates, and throws
 * the moment the car is first reported -- which is the app disappearing on launch in the car.
 *
 * Only [CarModeSession] is resolved here, so the rest of the module, which does need an Android
 * context, is never instantiated.
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
