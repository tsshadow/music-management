package nl.teunschriks.mumamobile.util

import android.content.Context
import android.util.TypedValue
import androidx.annotation.AttrRes

/**
 * Resolves a colour theme attribute against this context's theme.
 *
 * Code that needs the accent must go through here rather than through
 * `getColor(R.color.spotify_green)`: the accent is a theme attribute now, and a direct
 * colour reference would stay green under the blue theme.
 */
fun Context.themeColor(@AttrRes attrRes: Int): Int = TypedValue()
    .apply { theme.resolveAttribute(attrRes, this, true) }
    .data
