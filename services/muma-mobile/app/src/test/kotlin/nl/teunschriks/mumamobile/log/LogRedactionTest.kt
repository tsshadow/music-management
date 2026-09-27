package nl.teunschriks.mumamobile.log

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldContain
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

    /** The INFO line `CachedDataSource.open` wrote for every stream (bug report 054). */
    @Test
    fun `the credentials in a logged stream DataSpec are masked`() {
        val line = "CachedDatasource: Open: DataSpec[GET https://music.example.com/rest/stream.view" +
            "?id=tr-1&u=user&c=MuMa&f=json&v=1.16.1&p=enc:68756e74657232&maxBitRate=0, 0, -1, null, 0]"

        val redacted = LogRedaction.redactUrl(line)

        redacted shouldBeEqualTo "CachedDatasource: Open: DataSpec[GET https://music.example.com/rest/stream.view" +
            "?id=tr-1&u=<redacted>&c=MuMa&f=json&v=1.16.1&p=<redacted>&maxBitRate=0, 0, -1, null, 0]"
    }

    @Test
    fun `the salted token, its salt and an api key are masked too`() {
        val url = "https://x/rest/ping.view?t=26719a1196d2a940705a59634eb18eab&s=c19b2d&apiKey=abc123"

        LogRedaction.redactUrl(url) shouldBeEqualTo
            "https://x/rest/ping.view?t=<redacted>&s=<redacted>&apiKey=<redacted>"
    }

    @Test
    fun `ordinary parameters and text that merely ends in p= are left alone`() {
        val text = "stop=now https://x/rest/getAlbum.view?id=42&size=300 map=1"

        LogRedaction.redactUrl(text) shouldBeEqualTo text
    }

    @Test
    fun `a credential header line is masked`() {
        val redacted = LogRedaction.redact("X-API-Key: 444e005eefa57d15\nAuthorization: Basic dXNlcjpwYXNz\nAccept: */*")

        redacted shouldNotContain "444e005e"
        redacted shouldNotContain "dXNlcjpwYXNz"
        redacted.lines() shouldBeEqualTo listOf("X-API-Key: <redacted>", "Authorization: <redacted>", "Accept: */*")
    }

    @Test
    fun `redacting twice changes nothing`() {
        val once = LogRedaction.redact("GET https://x/rest/ping.view?u=user&p=enc:6869\nX-API-Key: abc")

        LogRedaction.redact(once) shouldBeEqualTo once
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

    /** The Subsonic token answer and a web action detail are JSON; bug report 103. */
    @Test
    fun `a credential member of a JSON object is masked`() {
        val line = """{"status":"ok","username":"user","token":"s3cr3t-subsonic-token"}"""

        val redacted = LogRedaction.redact(line)

        redacted shouldBeEqualTo """{"status":"ok","username":"user","token":"<redacted>"}"""
        LogRedaction.redact(redacted) shouldBeEqualTo redacted
    }

    @Test
    fun `a JSON credential with an escaped quote is masked whole`() {
        val redacted = LogRedaction.redact("""{"password" : "a\"b", "x": "y"}""")

        redacted shouldBeEqualTo """{"password" : "<redacted>", "x": "y"}"""
    }

    @Test
    fun `a token-signed stream URL keeps neither the hash nor the salt`() {
        val redacted = LogRedaction.redactUrl("https://x/rest/stream.view?id=1&u=user&t=0a1b2c&s=f00d&v=1.16.1")

        redacted shouldNotContain "0a1b2c"
        redacted shouldNotContain "f00d"
    }

    /** Issue #101: a failed password change quotes its URL, and the new password is in the query. */
    @Test
    fun `the password of an updateUser URL is masked`() {
        val line = "js.error {\"message\":\"GET https://x/rest/updateUser?u=user&t=0a1b&s=f0&username=user&password=hunter2 failed\"}"

        val redacted = LogRedaction.redact(line)

        redacted shouldNotContain "hunter2"
        redacted shouldContain "password=<redacted>"
        LogRedaction.redact(redacted) shouldBeEqualTo redacted
    }

    /** The shell's saveCredentials carries the MuMa key since issue #101; it never reaches a report. */
    @Test
    fun `the MuMa key handed to the shell is masked in a JSON detail`() {
        val redacted = LogRedaction.redact("""{"username":"user","mumaApiKey":"abc123","signedIn":true}""")

        redacted shouldBeEqualTo """{"username":"user","mumaApiKey":"<redacted>","signedIn":true}"""
    }
}
