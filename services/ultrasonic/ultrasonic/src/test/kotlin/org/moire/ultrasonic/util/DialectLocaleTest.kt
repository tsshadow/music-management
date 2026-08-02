package org.moire.ultrasonic.util

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.moire.ultrasonic.R
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Brabants and Sallands have no language code of their own, so they ride along on Dutch with a
 * region that Dutch speakers never have set: nl-BQ and nl-CW. Neither a three letter code (nds)
 * nor a BCP 47 variant (nl-NL-brabant) survives resource matching, and a locale that is missing
 * from [resourceConfigurations] in build.gradle is stripped from the APK entirely — so both the
 * qualifier and the whitelist are worth pinning down.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class)
class DialectLocaleTest {

    private fun string(id: Int): String = RuntimeEnvironment.getApplication().getString(id)

    @Test
    @Config(qualifiers = "nl-rBQ")
    fun `brabants resolves to its own resources`() {
        string(R.string.buttons_play) `should be equal to` "Afspele"
    }

    @Test
    @Config(qualifiers = "nl-rCW")
    fun `sallands resolves to its own resources`() {
        string(R.string.buttons_play) `should be equal to` "Speulen"
    }

    @Test
    @Config(qualifiers = "nl")
    fun `plain dutch is unaffected by the dialect folders`() {
        // Dutch has to stay complete: anything it misses falls through to a dialect folder
        // rather than to English, because those are also Dutch as far as Android is concerned.
        string(R.string.buttons_play) `should be equal to` "Afspelen"
    }

    @Test
    @Config(qualifiers = "nl-rBQ")
    fun `dialects cover the strings this fork added itself`() {
        string(R.string.library_tab_labels) `should be equal to` "Labels"
        string(R.string.library_tab_artists) `should be equal to` "Artieste"
    }

    @Test
    fun `both dialects are offered in the language picker`() {
        val context = RuntimeEnvironment.getApplication()
        val values = context.resources.getStringArray(R.array.languageValues).toList()
        val names = context.resources.getStringArray(R.array.languageNames).toList()

        values `should contain` "nl-BQ"
        values `should contain` "nl-CW"
        names.size `should be equal to` values.size
    }
}
