package nl.teunschriks.mumamobile.util

import android.content.Context
import android.util.TypedValue
import androidx.annotation.AttrRes

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
