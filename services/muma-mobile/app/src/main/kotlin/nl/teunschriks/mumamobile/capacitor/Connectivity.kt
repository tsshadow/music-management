/*
 * Connectivity.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/**
 * Whether the app can reach the server it is signed in to.
 *
 * The same two-part test `MusicServiceFactory.getMusicService` makes before it hands out the
 * offline service, so the web UI and the Kotlin services cannot disagree about which of the two
 * the app is in. Both halves matter and for different reasons: the listener can pick the
 * "Offline" server by hand on a perfectly good connection, and a phone on aeroplane mode has not
 * picked anything.
 *
 * @param activeServerIsOfflineDb the listener chose the offline library
 *   (`ActiveServerProvider.isOffline()`).
 * @param networkHasInternet a network with [NetworkCapabilities.NET_CAPABILITY_INTERNET] is up.
 * @param offlineChosen the listener picked "Offline verder" on the start-up check
 *   ([ServerReachability.offlineChosen]): the network may be fine, the server is not.
 */
fun hasRouteToServer(
    activeServerIsOfflineDb: Boolean,
    networkHasInternet: Boolean,
    offlineChosen: Boolean = false
): Boolean = !activeServerIsOfflineDb && networkHasInternet && !offlineChosen

/** Whether any network claiming internet access is up. Does not prove the server answers. */
fun ConnectivityManager.hasInternetCapability(): Boolean {
    val network = activeNetwork ?: return false
    val capabilities = getNetworkCapabilities(network) ?: return false
    return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
}
