package nl.teunschriks.mumamobile.voice

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * Whether the search box hands what was typed to the parser or searches for it literally.
 *
 * This is the guard on the one thing that can make the search box worse than it was: a parser that
 * quietly reinterprets an ordinary search.
 */
class SearchIntentTest {

    @Test
    fun `a single word is searched for, not parsed`() {
        searchIntentFor("Editors") `should be equal to` SearchIntent.FreeText("Editors")
    }

    @Test
    fun `a sentence is treated as a request`() {
        searchIntentFor("speel uptempo hardcore af") `should be equal to`
            SearchIntent.Request("speel uptempo hardcore af")
    }

    @Test
    fun `two words is already enough`() {
        searchIntentFor("Angerfist live") `should be equal to` SearchIntent.Request("Angerfist live")
    }

    @Test
    fun `surrounding space does not make a second word`() {
        searchIntentFor("   Editors  ") `should be equal to` SearchIntent.FreeText("Editors")
    }

    @Test
    fun `repeated spaces between two words still read as two`() {
        searchIntentFor("Angerfist    live") `should be equal to`
            SearchIntent.Request("Angerfist    live")
    }

    @Test
    fun `an empty query does nothing at all`() {
        searchIntentFor("").`should be null`()
        searchIntentFor("   ").`should be null`()
        searchIntentFor(null).`should be null`()
    }
}
