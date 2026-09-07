/*
 * AppGenreTints.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.coverart

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import org.koin.java.KoinJavaComponent

/**
 * The one genre-colour cache the app shares.
 *
 * The car and the home screen draw the same genres, and the colours are the same colours. Two
 * caches would mean two fetches an hour and, worse, a window where the car and the phone disagree
 * about what Hardstyle looks like because one of them refreshed first.
 *
 * The lookup is a blocking call on first use, so it belongs off the main thread. The car's browser
 * already answers on its own thread; the home screen draws its tiles on one.
 */
object AppGenreTints {

    val cache: GenreTintCache by lazy {
        GenreTintCache {
            KoinJavaComponent.get<SubsonicAPIClient>(SubsonicAPIClient::class.java)
                .mumaApi.api.getLibraryGenres().execute().body()
        }
    }
}
