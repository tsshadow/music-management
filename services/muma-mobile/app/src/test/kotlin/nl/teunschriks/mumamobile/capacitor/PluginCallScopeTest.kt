/*
 * PluginCallScopeTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import org.amshove.kluent.`should be equal to`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * The background work behind the Capacitor plugins. It used to run on a bare
 * `CoroutineScope(Dispatchers.IO)`: an exception crashed the process, the JavaScript promise was
 * never settled, and nothing was cancelled when the plugin went away. Every call now settles
 * exactly once, whichever way its work ends.
 */
@RunWith(RobolectricTestRunner::class)
class PluginCallScopeTest {

    private val calls = PluginCallScope("Test", Dispatchers.Unconfined)
    private val call: PluginCall = mockk(relaxed = true)

    @Test
    fun `a call that answers is resolved once`() {
        val data = JSObject().put("value", 1)

        calls.runCall(call) { answer -> answer.resolve(data) }

        verify(exactly = 1) { call.resolve(data) }
        verify(exactly = 0) { call.reject(any<String>()) }
    }

    @Test
    fun `an exception rejects the call instead of crashing the process`() {
        calls.runCall(call) { throw IllegalStateException("room is closed") }

        verify(exactly = 1) { call.reject("room is closed") }
        verify(exactly = 0) { call.resolve(any()) }
    }

    @Test
    fun `an exception after the answer does not settle the call a second time`() {
        calls.runCall(call) { answer ->
            answer.resolve()
            error("late failure")
        }

        verify(exactly = 1) { call.resolve() }
        verify(exactly = 0) { call.reject(any<String>()) }
    }

    @Test
    fun `one failing call leaves the others running`() {
        val other: PluginCall = mockk(relaxed = true)

        calls.runCall(call) { throw IllegalStateException("boom") }
        calls.runCall(other) { answer -> answer.resolve() }

        verify(exactly = 1) { other.resolve() }
    }

    @Test
    fun `destroying the plugin rejects a call that is still working`() {
        val never = CompletableDeferred<Unit>()
        calls.runCall(call) { answer ->
            never.await()
            answer.resolve()
        }

        calls.cancel()

        verify(exactly = 1) { call.reject(any<String>()) }
        verify(exactly = 0) { call.resolve() }
    }

    @Test
    fun `a call started after the plugin was destroyed is rejected, not left pending`() {
        calls.cancel()

        calls.runCall(call) { answer -> answer.resolve() }

        verify(exactly = 1) { call.reject(any<String>()) }
    }

    @Test
    fun `an answer settles only once`() {
        val answer = CallAnswer(call)

        answer.reject("first")
        answer.resolve()
        answer.reject("second")

        answer.isSettled `should be equal to` true
        verify(exactly = 1) { call.reject("first") }
        verify(exactly = 0) { call.resolve() }
    }
}
