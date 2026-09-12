package nl.teunschriks.mumamobile.util

import android.content.Context
import android.util.TypedValue
import androidx.annotation.AttrRes
import nl.teunschriks.mumamobile.R

/**
 * Resolves a colour theme attribute against this context's theme.
 *
 * Code that needs a themed colour must go through here rather than through `getColor(...)` on a
 * palette entry: every colour the app draws is a theme attribute now, and a direct colour
 * reference would keep the Spotify style's value under the MuMa style.
 */
fun Context.themeColor(@AttrRes attrRes: Int): Int = TypedValue()
    .apply { theme.resolveAttribute(attrRes, this, true) }
    .data

/**
 * The colour the app marks the current mode with: green for songs, blue for sets.
 *
 * One definition, because there were three and they disagreed. A selected track row asked
 * [Settings.isSetsMode] and got blue in sets mode; the sets toggle in the toolbar asked nobody and
 * went green while switching *to* sets, which is the one moment the blue is the point. Read per
 * call rather than cached: anything holding a colour outlives a mode switch.
 */
fun Context.brandColor(): Int = if (Settings.isSetsMode) {
    themeColor(R.attr.brandColorSets)
} else {
    themeColor(androidx.appcompat.R.attr.colorPrimary)
}
