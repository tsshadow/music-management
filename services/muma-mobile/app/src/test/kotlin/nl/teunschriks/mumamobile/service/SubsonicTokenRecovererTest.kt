package nl.teunschriks.mumamobile.service

import java.io.IOException
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import nl.teunschriks.mumamobile.data.SignOutEpoch
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeNull
import org.junit.After
import org.junit.Before
import org.junit.Test
import timber.log.Timber

/**
 * Pins [SubsonicTokenRecoverer]: one refetch per refusal, shared by concurrent callers, a back-off
 * so a refused account does not loop, a sign-out that wins over a late answer, and no token in
 * the log (issue #73, bug report 111).
 */
class SubsonicTokenRecovererTest {

    private var stored: String? = OLD_TOKEN
    private var now = 0L
    private val refetches = AtomicInteger()
    private val recoveries = AtomicInteger()
    private val logs: MutableList<String> = Collections.synchronizedList(mutableListOf())
    private val tree = object : Timber.Tree() {
        override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
            logs += message
        }
    }

    @Before
    fun plantTree() {
        Timber.plant(tree)
    }

    @After
    fun uprootTree() {
        Timber.uproot(tree)
    }

    private fun recoverer(refetch: () -> Unit) = SubsonicTokenRecoverer(
        refetch = {
            refetches.incrementAndGet()
            refetch()
        },
        storedToken = { stored },
        signOutEpoch = { SignOutEpoch.current() },
        onRecovered = { recoveries.incrementAndGet() },
        clock = { now },
        minIntervalMs = 30_000,
        failureBackoffMs = 300_000
    )

    @Test
    fun `a refused token triggers exactly one refetch and hands back the new token`() {
        val recoverer = recoverer { stored = NEW_TOKEN }

        recoverer.recover(OLD_TOKEN) shouldBeEqualTo NEW_TOKEN

        refetches.get() shouldBeEqualTo 1
        recoveries.get() shouldBeEqualTo 1
    }

    @Test
    fun `concurrent refusals share one refetch`() {
        val release = CountDownLatch(1)
        val recoverer = recoverer {
            release.await(5, TimeUnit.SECONDS)
            stored = NEW_TOKEN
        }
        val pool = Executors.newFixedThreadPool(CALLERS)
        val results = (1..CALLERS).map { pool.submit<String?> { recoverer.recover(OLD_TOKEN) } }
        // Let every caller reach the lock before the one refetch completes.
        Thread.sleep(200)
        release.countDown()

        results.map { it.get(5, TimeUnit.SECONDS) } shouldBeEqualTo List(CALLERS) { NEW_TOKEN }
        pool.shutdown()
        refetches.get() shouldBeEqualTo 1
        recoveries.get() shouldBeEqualTo 1
    }

    @Test
    fun `a refetch that returns the same token backs off instead of looping`() {
        val recoverer = recoverer { /* the server hands out the refused token again */ }

        recoverer.recover(OLD_TOKEN).shouldBeNull()
        now += 60_000
        recoverer.recover(OLD_TOKEN).shouldBeNull()

        refetches.get() shouldBeEqualTo 1
        recoveries.get() shouldBeEqualTo 0

        now += 300_000
        recoverer.recover(OLD_TOKEN).shouldBeNull()
        refetches.get() shouldBeEqualTo 2
    }

    @Test
    fun `a failing refetch keeps the stored token and backs off`() {
        val recoverer = recoverer { throw IOException("https://muma.example/api?secret=$NEW_TOKEN") }

        recoverer.recover(OLD_TOKEN).shouldBeNull()
        recoverer.recover(OLD_TOKEN).shouldBeNull()

        stored shouldBeEqualTo OLD_TOKEN
        refetches.get() shouldBeEqualTo 1
    }

    @Test
    fun `a replaced token refused again within the minimum interval is not refetched`() {
        var next = NEW_TOKEN
        val recoverer = recoverer { stored = next }
        recoverer.recover(OLD_TOKEN) shouldBeEqualTo NEW_TOKEN

        next = "third-token-0123456789"
        now += 1_000
        recoverer.recover(NEW_TOKEN).shouldBeNull()

        refetches.get() shouldBeEqualTo 1
    }

    @Test
    fun `a sign-out during the refetch discards the answer`() {
        val recoverer = recoverer {
            stored = NEW_TOKEN
            SignOutEpoch.signOut { stored = null }
        }

        recoverer.recover(OLD_TOKEN).shouldBeNull()

        recoveries.get() shouldBeEqualTo 0
        stored.shouldBeNull()
    }

    @Test
    fun `a sign-out and new sign-in during the refetch still discards the answer`() {
        val recoverer = recoverer {
            SignOutEpoch.signOut { stored = null }
            stored = NEW_TOKEN
        }

        recoverer.recover(OLD_TOKEN).shouldBeNull()

        recoveries.get() shouldBeEqualTo 0
    }

    @Test
    fun `nothing to recover without a stored token`() {
        stored = null
        val recoverer = recoverer { stored = NEW_TOKEN }

        recoverer.recover(OLD_TOKEN).shouldBeNull()

        refetches.get() shouldBeEqualTo 0
    }

    @Test
    fun `the token never reaches the log`() {
        recoverer { stored = NEW_TOKEN }.recover(OLD_TOKEN)
        recoverer { }.recover(NEW_TOKEN)
        recoverer { throw IOException("secret=$OLD_TOKEN") }.recover(OLD_TOKEN)

        logs.isEmpty().shouldBeFalse()
        logs.any { it.contains(OLD_TOKEN) || it.contains(NEW_TOKEN) }.shouldBeFalse()
    }

    @Test
    fun `sign-out epoch refuses a store that raced a sign-out`() {
        val epoch = SignOutEpoch.current()
        SignOutEpoch.signOut { }

        SignOutEpoch.storeIfUnchanged(epoch) { stored = NEW_TOKEN }.shouldBeFalse()
        stored shouldBeEqualTo OLD_TOKEN
    }

    private companion object {
        const val OLD_TOKEN = "old-token-0123456789abcdef"
        const val NEW_TOKEN = "new-token-0123456789abcdef"
        const val CALLERS = 8
    }
}
