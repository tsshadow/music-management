/*
 * ManualContentTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.manual

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import androidx.appcompat.view.ContextThemeWrapper
import androidx.appcompat.widget.Toolbar
import androidx.core.content.ContextCompat
import nl.teunschriks.mumamobile.R
import org.amshove.kluent.`should be greater than`
import org.amshove.kluent.`should be true`
import org.amshove.kluent.`should not be null`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The manual is a table of resource ids. Nothing in Kotlin fails when one of them goes away: a
 * renamed drawable or a string that only ever landed in the Dutch file compiles fine and lands as
 * a blank chapter, on a screen people open exactly when they are already lost.
 *
 * Robolectric draws nothing; resolving is all this checks, and all it needs to.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class)
class ManualContentTest {

    private fun themed(theme: Int): Context = ContextThemeWrapper(RuntimeEnvironment.getApplication(), theme)

    private fun spotify(): Context = themed(R.style.UltrasonicTheme_Spotify)

    @Test
    fun `every chapter has a title, a body and an icon that resolve`() {
        val context = spotify()

        manualChapters.size `should be greater than` 0

        manualChapters.forEach { chapter ->
            context.getString(chapter.title).isNotBlank().`should be true`()
            context.getString(chapter.body).isNotBlank().`should be true`()
            ContextCompat.getDrawable(context, chapter.icon).`should not be null`()
        }
    }

    @Test
    fun `every screenshot a chapter names exists`() {
        val context = spotify()

        manualChapters.mapNotNull { it.screenshot }.forEach { screenshot ->
            ContextCompat.getDrawable(context, screenshot).`should not be null`()
        }
    }

    /**
     * Half an action is a button that does nothing, or a destination with no way to reach it.
     */
    @Test
    fun `an action carries both a label and a destination`() {
        val context = spotify()

        manualChapters.forEach { chapter ->
            (chapter.actionLabel == null) shouldMatch (chapter.actionDestination == null)
            chapter.actionLabel?.let { context.getString(it).isNotBlank().`should be true`() }
        }
    }

    @Test
    fun `the manual screens inflate under both styles`() {
        listOf(R.style.UltrasonicTheme_Spotify, R.style.UltrasonicTheme_Muma).forEach { style ->
            val context = themed(style)
            val inflater = LayoutInflater.from(context)

            val screen = inflater.inflate(R.layout.manual, null)
            screen.findViewById<View>(R.id.manual_list).`should not be null`()
            screen.findViewById<View>(R.id.manual_intro).`should not be null`()

            val row = inflater.inflate(R.layout.manual_chapter_row, null)
            row.findViewById<View>(R.id.manual_chapter_title).`should not be null`()
            row.findViewById<View>(R.id.manual_chapter_body).`should not be null`()
            row.findViewById<View>(R.id.manual_chapter_image).`should not be null`()
            row.findViewById<View>(R.id.manual_chapter_action).`should not be null`()

            val dialog = inflater.inflate(R.layout.manual_screenshot_dialog, null)
            dialog.findViewById<View>(R.id.manual_screenshot_full).`should not be null`()
        }
    }

    /**
     * The overflow menu reaches the manual through [androidx.navigation.ui.onNavDestinationSelected],
     * which matches the menu item id against a destination id. Drop the item and Help is
     * unreachable; the screen stays in the graph and nothing else complains.
     */
    @Test
    fun `the overflow menu offers help`() {
        val toolbar = Toolbar(spotify())
        toolbar.inflateMenu(R.menu.search_view_menu)

        toolbar.menu.findItem(R.id.manualFragment).`should not be null`()
    }

    private infix fun Boolean.shouldMatch(other: Boolean) {
        (this == other).`should be true`()
    }
}
