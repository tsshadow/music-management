package nl.teunschriks.mumamobile.log

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldNotContain
import org.junit.Test

/**
 * The startup settings dump wrote the password and the MuMa API key into the ring buffer, and
 * every diagnostics report uploaded it. Reports 34 and 35 reached the server that way.
 */
class LogRedactionTest {

    @Test
    fun `a credential setting is masked when it is logged`() {
        LogRedaction.settingValue("staticPassword", "hunter2") shouldBeEqualTo LogRedaction.MASK
        LogRedaction.settingValue("mumaApiKey", "444e005e") shouldBeEqualTo LogRedaction.MASK
    }

    @Test
    fun `an ordinary setting is logged as it is`() {
        LogRedaction.settingValue("cacheSize", 250000) shouldBeEqualTo "250000"
        LogRedaction.settingValue("staticUserName", "user") shouldBeEqualTo "user"
    }

    @Test
    fun `an empty credential is not masked -- that it is empty is worth knowing`() {
        LogRedaction.settingValue("staticPassword", "") shouldBeEqualTo ""
    }

    @Test
    fun `a ring buffer written by an older build is redacted on the way out`() {
        val persisted = """
            14:41:06.310 D/UApp${'$'}onCreate: mumaApiKey: 444e005eefa57d15
            14:41:06.310 D/UApp${'$'}onCreate: defaultSongs: 10
            14:41:06.313 D/UApp${'$'}onCreate: staticPassword: 444e005eefa57d15
        """.trimIndent()

        val redacted = LogRedaction.redact(persisted)

        redacted shouldNotContain "444e005e"
        redacted.lines() shouldBeEqualTo listOf(
            "14:41:06.310 D/UApp${'$'}onCreate: mumaApiKey: <redacted>",
            "14:41:06.310 D/UApp${'$'}onCreate: defaultSongs: 10",
            "14:41:06.313 D/UApp${'$'}onCreate: staticPassword: <redacted>"
        )
    }
}
