/*
 * EqualizerMapping.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.capacitor

import kotlin.math.roundToInt

/** Android's `Equalizer` speaks millibels; the web contract speaks decibels. */
private const val MILLIBELS_PER_DECIBEL = 100f

/**
 * Spreads the web equalizer's curve over however many bands the device's equalizer has.
 *
 * The web player draws a fixed ten-band graphic equalizer built on Web Audio. Android's
 * `android.media.audiofx.Equalizer` has whatever number of bands the hardware offers — five on
 * most phones — at frequencies it chooses itself. There is no honest one-to-one mapping, so the
 * curve is resampled: native band `i` takes the web band it sits nearest to in the ordering.
 * Same shape, fewer points.
 *
 * There is no preamp in the Android API either, so the preamp is folded into every band. That is
 * what a preamp does to the resulting curve anyway; what it costs is headroom, and clamping to
 * the device's own [minMillibels]/[maxMillibels] is what keeps the shape from being destroyed
 * when it runs out.
 *
 * @param gains one gain in dB per web band, in ascending frequency order.
 * @param preamp dB added to every band.
 * @param bandCount how many bands the device's equalizer has.
 */
fun nativeBandGains(
    gains: List<Float>,
    preamp: Float,
    bandCount: Int,
    minMillibels: Short,
    maxMillibels: Short
): ShortArray {
    if (bandCount <= 0) return ShortArray(0)
    val curve = if (gains.isEmpty()) listOf(0f) else gains
    return ShortArray(bandCount) { index ->
        val source = if (bandCount == 1) {
            0
        } else {
            ((index.toFloat() / (bandCount - 1)) * (curve.size - 1)).roundToInt()
        }
        val millibels = (curve[source.coerceIn(0, curve.size - 1)] + preamp) * MILLIBELS_PER_DECIBEL
        millibels.roundToInt().coerceIn(minMillibels.toInt(), maxMillibels.toInt()).toShort()
    }
}
