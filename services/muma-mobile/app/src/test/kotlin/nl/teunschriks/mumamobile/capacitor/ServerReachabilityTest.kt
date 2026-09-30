/*
 * ServerReachabilityTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Test

/**
 * The start-up check's classifier (docs/designs/app-start-reachability/): which of the four
 * answers a ping and Android's network state add up to. The distinction that matters most is
 * the last one -- a server that refuses the credentials is reachable, and must lead to the login
 * page rather than to "offline".
 */
class ServerReachabilityTest {

    @After
    fun resetChoice() {
        ServerReachability.offlineChosen = false
    }

    @Test
    fun `an ok ping is reachable, whatever Android says about the network`() {
        ServerReachability.classify(networkUp = true, PingOutcome.Ok) shouldBeEqualTo Reachability.REACHABLE
        // A home LAN without internet still reaches a server on it.
        ServerReachability.classify(networkUp = false, PingOutcome.Ok) shouldBeEqualTo Reachability.REACHABLE
    }

    @Test
    fun `refused credentials are an auth failure, not offline`() {
        for (code in listOf(40, 41, 42, 43, 44)) {
            ServerReachability.classify(true, PingOutcome.Failed(code)) shouldBeEqualTo Reachability.AUTH_FAILED
        }
        ServerReachability.classify(true, PingOutcome.Http(401)) shouldBeEqualTo Reachability.AUTH_FAILED
        ServerReachability.classify(true, PingOutcome.Http(403)) shouldBeEqualTo Reachability.AUTH_FAILED
    }

    @Test
    fun `any other failed envelope still proves the server answered`() {
        ServerReachability.classify(true, PingOutcome.Failed(10)) shouldBeEqualTo Reachability.REACHABLE
        ServerReachability.classify(true, PingOutcome.Failed(0)) shouldBeEqualTo Reachability.REACHABLE
        ServerReachability.classify(true, PingOutcome.Http(500)) shouldBeEqualTo Reachability.REACHABLE
        ServerReachability.classify(true, PingOutcome.Http(404)) shouldBeEqualTo Reachability.REACHABLE
    }

    @Test
    fun `a proxy answering for a server that is down is unreachable`() {
        for (status in listOf(502, 503, 504)) {
            ServerReachability.classify(true, PingOutcome.Http(status)) shouldBeEqualTo Reachability.SERVER_UNREACHABLE
        }
    }

    @Test
    fun `no answer splits on the network state`() {
        ServerReachability.classify(true, PingOutcome.Timeout) shouldBeEqualTo Reachability.SERVER_UNREACHABLE
        ServerReachability.classify(true, PingOutcome.NetworkError) shouldBeEqualTo Reachability.SERVER_UNREACHABLE
        ServerReachability.classify(false, PingOutcome.Timeout) shouldBeEqualTo Reachability.NO_NETWORK
        ServerReachability.classify(false, PingOutcome.NetworkError) shouldBeEqualTo Reachability.NO_NETWORK
    }

    @Test
    fun `no ping at all never blocks a start that has a network`() {
        ServerReachability.classify(true, null) shouldBeEqualTo Reachability.REACHABLE
        ServerReachability.classify(false, null) shouldBeEqualTo Reachability.NO_NETWORK
    }

    @Test
    fun `an HTTP answer becomes an outcome by status first, then by envelope`() {
        ServerReachability.outcomeOf(200, ok = true, errorCode = null) shouldBeEqualTo PingOutcome.Ok
        ServerReachability.outcomeOf(200, ok = false, errorCode = 40) shouldBeEqualTo PingOutcome.Failed(40)
        ServerReachability.outcomeOf(200, ok = false, errorCode = null) shouldBeEqualTo PingOutcome.Failed(0)
        // A captive portal's HTML page: something answered, but not the server.
        ServerReachability.outcomeOf(200, ok = null, errorCode = null) shouldBeEqualTo PingOutcome.NetworkError
        ServerReachability.outcomeOf(502, ok = null, errorCode = null) shouldBeEqualTo PingOutcome.Http(502)
    }

    @Test
    fun `choosing offline takes the route away even on a good network`() {
        hasRouteToServer(activeServerIsOfflineDb = false, networkHasInternet = true, offlineChosen = true) shouldBeEqualTo false
        hasRouteToServer(activeServerIsOfflineDb = false, networkHasInternet = true, offlineChosen = false) shouldBeEqualTo true
        // The default keeps every existing caller's answer.
        hasRouteToServer(activeServerIsOfflineDb = false, networkHasInternet = true) shouldBeEqualTo true
    }
}
