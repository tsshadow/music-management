/*
 * UiScaleHelper.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.util

import android.content.Context
import android.content.ContextWrapper
import android.content.res.Configuration

/**
 * Simple Helper class to "wrap" a context with a scaled display density.
 *
 * Lowering densityDpi makes every dp and sp resolve to fewer physical pixels, which shrinks the
 * whole interface at once - the same mechanism as the system wide "Display size" setting, but
 * scoped to this app. It is the only way to resize the UI globally, as the layouts use hardcoded
 * dp values instead of a dimension resource per size.
 */
class UiScaleHelper(base: Context?) : ContextWrapper(base) {
    companion object {
        /** Below this the touch targets get unusable, above it there is nothing left to scale. */
        private const val MIN_SCALE_PERCENT = 50
        private const val MAX_SCALE_PERCENT = 100

        fun wrap(ctx: Context?, scalePercent: Int): ContextWrapper {
            var context = ctx
            val scale = scalePercent.coerceIn(MIN_SCALE_PERCENT, MAX_SCALE_PERCENT)

            if (context != null && scale != MAX_SCALE_PERCENT) {
                val config = Configuration(context.resources.configuration)
                config.densityDpi = config.densityDpi * scale / 100
                context = context.createConfigurationContext(config)
            }
            return UiScaleHelper(context)
        }
    }
}
