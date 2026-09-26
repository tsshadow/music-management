package nl.teunschriks.mumamobile.service

import org.amshove.kluent.`should be equal to`
import org.junit.Test

/** The per-key settings write's helpers (issue #39, bug report 116). */
class MumaSettingsChangesTest {

    @Test
    fun `a changes object is parsed as-is for the PATCH body`() {
        settingsChangesObject("""{"a":1,"b":[2]}""").toString() `should be equal to` """{"a":1,"b":[2]}"""
    }

    @Test(expected = IllegalArgumentException::class)
    fun `changes that are not a JSON object are refused rather than sent`() {
        settingsChangesObject("""[1,2]""")
    }

    @Test
    fun `the fallback merge replaces only the changed top-level keys`() {
        val blob = """{"language":"nl","setResume":{"work:1":{}},"favoriteGenres":["Old"]}"""

        mergeSettingsChanges(blob, """{"favoriteGenres":["New"]}""") `should be equal to`
            """{"language":"nl","setResume":{"work:1":{}},"favoriteGenres":["New"]}"""
    }

    @Test
    fun `the fallback merge treats a missing or broken blob as empty`() {
        mergeSettingsChanges(null, """{"a":1}""") `should be equal to` """{"a":1}"""
        mergeSettingsChanges("garbage", """{"a":1}""") `should be equal to` """{"a":1}"""
        mergeSettingsChanges("[1]", """{"a":1}""") `should be equal to` """{"a":1}"""
    }
}
