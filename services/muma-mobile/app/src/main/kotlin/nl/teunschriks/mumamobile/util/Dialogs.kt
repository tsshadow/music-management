/*
 * Dialogs.kt
 * Copyright (C) 2009-2021 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.util

import android.app.Activity
import android.content.Context
import android.view.ContextThemeWrapper
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.lang.ref.WeakReference
import nl.teunschriks.mumamobile.R
import timber.log.Timber

/**
 * MaterialAlertDialogBuilder throws IllegalArgumentException from its constructor when the given
 * context does not carry an AppCompat descendant theme. That happens whenever a dialog is built
 * from a non-Activity context, e.g. when a background coroutine fails and the error handler only
 * has the application context. Wrapping in the app theme makes the builder constructible.
 */
internal fun Context.withUltrasonicTheme(): Context =
    if (this is Activity) this else ContextThemeWrapper(this, R.style.UltrasonicTheme_Dark)

/*
 * InfoDialog can be used to show some information to the user. Typically it cannot be cancelled,
 * only dismissed via OK.
 */
open class InfoDialog(
    context: Context,
    message: CharSequence?,
    activity: Activity? = null,
    private val finishActivityOnClose: Boolean = false
) {
    private val activityRef: WeakReference<Activity?> = WeakReference(activity)
    protected val dialogContext: Context = (activity ?: context).withUltrasonicTheme()
    protected val dialogMessage: CharSequence? = message

    // Built lazily so that a context which still cannot host a dialog fails inside show()'s
    // catch block instead of taking the process down from the constructor.
    open val builder: MaterialAlertDialogBuilder by lazy { Builder(dialogContext, dialogMessage) }

    fun show() {
        // If the app was put into the background in the meantime this would fail
        try {
            builder.setOnCancelListener {
                if (finishActivityOnClose) {
                    activityRef.get()?.finish()
                }
            }
            builder.setPositiveButton(R.string.common_ok) { _, _ ->
                if (finishActivityOnClose) {
                    activityRef.get()?.finish()
                }
            }
            builder.create().show()
        } catch (all: Exception) {
            Timber.w(all, "Failed to create dialog")
            showFallbackToast()
        }
    }

    private fun showFallbackToast() {
        val text = dialogMessage ?: return
        try {
            Toast.makeText(dialogContext, text, Toast.LENGTH_LONG).show()
        } catch (all: Exception) {
            Timber.w(all, "Failed to show fallback toast")
        }
    }

    class Builder(context: Context) : MaterialAlertDialogBuilder(context) {

        constructor(context: Context, message: CharSequence?) : this(context) {
            setMessage(message)
        }

        init {
            setIcon(R.drawable.ic_baseline_info)
            setTitle(R.string.common_confirm)
            setPositiveButton(R.string.common_ok) { _, _ ->
                // Just close it
            }
        }
    }
}

/*
 * ErrorDialog can be used to show some an error to the user.
 * Typically it cannot be cancelled, only dismissed via OK.
 */
class ErrorDialog(
    context: Context,
    message: CharSequence?,
    activity: Activity? = null,
    finishActivityOnClose: Boolean = false
) : InfoDialog(context, message, activity, finishActivityOnClose) {

    override val builder: MaterialAlertDialogBuilder by lazy {
        Builder(dialogContext, dialogMessage)
    }

    class Builder(context: Context) : MaterialAlertDialogBuilder(context) {
        constructor(context: Context, message: CharSequence?) : this(context) {
            setMessage(message)
        }

        init {
            setIcon(R.drawable.ic_baseline_warning)
            setTitle(R.string.error_label)
            setPositiveButton(R.string.common_ok) { _, _ ->
                // Just close it
            }
        }
    }
}

/*
 * ConfirmationDialog can be used to present a choice to the user.
 * Typically it will be cancelable..
 */
class ConfirmationDialog(
    context: Context,
    message: CharSequence?,
    activity: Activity? = null,
    finishActivityOnClose: Boolean = false
) : InfoDialog(context, message, activity, finishActivityOnClose) {
    override val builder: MaterialAlertDialogBuilder by lazy {
        Builder(dialogContext, dialogMessage)
    }

    companion object {
        fun show(
            context: Context,
            title: Int,
            message: Int,
            positiveButton: Int,
            negativeButton: Int,
            onPositive: () -> Unit
        ): MaterialAlertDialogBuilder {
            val builder = Builder(context.withUltrasonicTheme())
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton(positiveButton) { _, _ -> onPositive() }
                .setNegativeButton(negativeButton) { _, _ -> }
            builder.show()
            return builder
        }
    }

    class Builder(context: Context) : MaterialAlertDialogBuilder(context) {
        constructor(context: Context, message: CharSequence?) : this(context) {
            setMessage(message)
        }

        init {
            setIcon(R.drawable.ic_baseline_info)
            setTitle(R.string.common_confirm)
            setCancelable(true)

            setPositiveButton(R.string.common_confirm) { _, _ ->
                // Gets overwritten
            }

            setNegativeButton(R.string.common_cancel) { _, _ ->
                // Just close it
            }
        }
    }
}
