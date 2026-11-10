package nl.teunschriks.mumamobile.service.androidauto

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import nl.teunschriks.mumamobile.capacitor.Reachability
import nl.teunschriks.mumamobile.capacitor.ServerCheck
import nl.teunschriks.mumamobile.service.androidauto.CarServerCheck.Companion.RECHECK_MS
import nl.teunschriks.mumamobile.service.androidauto.CarServerCheck.Companion.TRUST_MS
import nl.teunschriks.mumamobile.service.androidauto.CarServerCheck.Companion.route
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The car browses the downloaded library while the server is known to be down, also outside
 * offline mode (docs/designs/offline-followups/), and never waits for a check while browsing.
 */
class CarServerCheckTest {

    private val now = 1_000_000L

    private fun check(state: Reachability, ageMs: Long) = ServerCheck(state, now - ageMs)

    @Test
    fun `offline mode chosen always browses offline and leaves the asking to the web`() {
        route(true, null, now) `should be equal to` CarRoute(offline = true, recheck = false)
        route(true, check(Reachability.REACHABLE, 0), now) `should be equal to` CarRoute(offline = true, recheck = false)
    }

    @Test
    fun `without any check the car stays online and asks`() {
        route(false, null, now) `should be equal to` CarRoute(offline = false, recheck = true)
    }

    @Test
    fun `a recent unreachable answer browses offline, and asks again once it ages`() {
        for (state in listOf(Reachability.SERVER_UNREACHABLE, Reachability.NO_NETWORK)) {
            route(false, check(state, 0), now) `should be equal to` CarRoute(offline = true, recheck = false)
            route(false, check(state, RECHECK_MS), now) `should be equal to` CarRoute(offline = true, recheck = true)
            route(false, check(state, TRUST_MS - 1), now) `should be equal to` CarRoute(offline = true, recheck = true)
        }
    }

    @Test
    fun `an unreachable answer that is too old is not trusted`() {
        route(false, check(Reachability.SERVER_UNREACHABLE, TRUST_MS), now) `should be equal to`
            CarRoute(offline = false, recheck = true)
    }

    @Test
    fun `a server that answered is browsed online, and asked again now and then`() {
        for (state in listOf(Reachability.REACHABLE, Reachability.AUTH_FAILED)) {
            route(false, check(state, RECHECK_MS), now) `should be equal to` CarRoute(offline = false, recheck = false)
            route(false, check(state, TRUST_MS), now) `should be equal to` CarRoute(offline = false, recheck = true)
        }
    }

    @Test
    fun `connecting runs a check only when the last answer is old or missing`() = runBlocking<Unit> {
        var last: ServerCheck? = null
        var checks = 0
        val car = CarServerCheck(
            scope = CoroutineScope(Dispatchers.Unconfined),
            lastCheck = { last },
            offlineChosen = { false },
            nowMs = { now },
            check = {
                checks++
                last = ServerCheck(Reachability.SERVER_UNREACHABLE, now)
                Reachability.SERVER_UNREACHABLE
            }
        )

        car.ensureFresh()
        checks `should be equal to` 1
        car.prefersOffline() `should be equal to` true

        car.ensureFresh()
        checks `should be equal to` 1

        last = ServerCheck(Reachability.REACHABLE, now - RECHECK_MS)
        car.ensureFresh()
        checks `should be equal to` 2
    }

    @Test
    fun `browsing on an ageing answer checks in the background and follows the new answer`() {
        var last: ServerCheck? = ServerCheck(Reachability.SERVER_UNREACHABLE, now - RECHECK_MS)
        var checks = 0
        val car = CarServerCheck(
            scope = CoroutineScope(Dispatchers.Unconfined),
            lastCheck = { last },
            offlineChosen = { false },
            nowMs = { now },
            check = {
                checks++
                last = ServerCheck(Reachability.REACHABLE, now)
                Reachability.REACHABLE
            }
        )

        // The call that started the check still gets the answer it had.
        car.prefersOffline() `should be equal to` true
        checks `should be equal to` 1
        car.prefersOffline() `should be equal to` false
        checks `should be equal to` 1
    }

    @Test
    fun `a failing check leaves the last answer in place`() = runBlocking<Unit> {
        val car = CarServerCheck(
            scope = CoroutineScope(Dispatchers.Unconfined),
            lastCheck = { null },
            offlineChosen = { false },
            nowMs = { now },
            check = { error("no client") }
        )

        car.ensureFresh()
        car.prefersOffline() `should be equal to` false
    }

    @Test
    fun `in offline mode connecting runs no check`() = runBlocking<Unit> {
        var checks = 0
        val car = CarServerCheck(
            scope = CoroutineScope(Dispatchers.Unconfined),
            lastCheck = { null },
            offlineChosen = { true },
            nowMs = { now },
            check = {
                checks++
                Reachability.REACHABLE
            }
        )

        car.ensureFresh()
        checks `should be equal to` 0
    }
}
