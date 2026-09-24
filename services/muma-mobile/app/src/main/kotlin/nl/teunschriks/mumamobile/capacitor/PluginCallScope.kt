/*
 * PluginCallScope.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import com.getcapacitor.JSObject
import com.getcapacitor.PluginCall
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import timber.log.Timber

/**
 * The background work of one Capacitor plugin.
 *
 * The plugins used to launch on a bare `CoroutineScope(Dispatchers.IO)`: no `SupervisorJob`, no
 * exception handler, never cancelled. An exception in one of those blocks went to the thread's
 * uncaught-exception handler -- a process crash -- and the JavaScript promise waiting on the call
 * never settled. Here a failure is logged and rejects the call, one failing call does not cancel
 * its siblings, and [cancel] (from the plugin's `handleOnDestroy`) ends whatever is still running
 * and rejects the calls it was answering.
 *
 * @param pluginName used in log lines and rejection messages.
 * @param dispatcher where the work runs; tests pass an immediate one.
 */
class PluginCallScope(
    private val pluginName: String,
    dispatcher: CoroutineDispatcher = Dispatchers.IO
) {
    private val job = SupervisorJob()

    // Only reached by a Throwable that is not an Exception (runCall catches those) or by work
    // started with launch(); either way it is logged instead of taking the process down.
    private val handler = CoroutineExceptionHandler { _, failure ->
        Timber.e(failure, "%s: background work failed", pluginName)
    }

    private val scope = CoroutineScope(job + dispatcher + handler)

    /** Background work that answers no call; a failure is logged, never fatal. */
    fun launch(block: suspend CoroutineScope.() -> Unit): Job = scope.launch(block = block)

    /** Runs [block] for [call]; see the [CallAnswer] overload. */
    fun runCall(call: PluginCall, block: suspend CoroutineScope.(CallAnswer) -> Unit): Job = runCall(CallAnswer(call), block)

    /**
     * Runs [block] in the background and makes sure [answer] is settled exactly once: [block]
     * resolves or rejects it itself, an exception out of [block] rejects it with the exception's
     * message, and cancellation (the plugin being destroyed) rejects it as cancelled. Whatever
     * comes second is ignored by [CallAnswer].
     */
    fun runCall(answer: CallAnswer, block: suspend CoroutineScope.(CallAnswer) -> Unit): Job {
        val work = scope.launch {
            try {
                block(answer)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (@Suppress("TooGenericExceptionCaught") failure: Exception) {
                Timber.w(failure, "%s: call failed", pluginName)
                answer.reject(failure.message ?: failure.javaClass.simpleName)
            }
        }
        work.invokeOnCompletion { cause ->
            when (cause) {
                null -> Unit
                is CancellationException -> answer.reject("$pluginName: cancelled, the plugin was shut down")
                else -> answer.reject("$pluginName: ${cause.javaClass.simpleName}")
            }
        }
        return work
    }

    /** Cancels everything still running; called from the plugin's `handleOnDestroy`. */
    fun cancel() {
        job.cancel()
    }
}

/**
 * A [PluginCall] that can be settled only once. The first `resolve` or `reject` goes through to
 * Capacitor; any later one is dropped, so a failure after an answer cannot contradict it.
 */
class CallAnswer(private val call: PluginCall) {
    private val settled = AtomicBoolean(false)

    /** Whether the call has been resolved or rejected already. */
    val isSettled: Boolean get() = settled.get()

    /** Resolves the call with [data], or with no data, unless it was settled before. */
    fun resolve(data: JSObject? = null) {
        if (!settled.compareAndSet(false, true)) return
        if (data == null) call.resolve() else call.resolve(data)
    }

    /** Rejects the call with [message], unless it was settled before. */
    fun reject(message: String) {
        if (!settled.compareAndSet(false, true)) return
        call.reject(message)
    }
}
