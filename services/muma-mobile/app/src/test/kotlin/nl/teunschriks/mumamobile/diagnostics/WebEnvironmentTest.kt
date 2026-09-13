package nl.teunschriks.mumamobile.diagnostics

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.After
import org.junit.Test

class WebEnvironmentTest {

    @After
    fun reset() = WebEnvironment.reset()

    @Test
    fun `nothing identified yet reads as the legacy UI`() {
        WebEnvironment.uiVariant() shouldBeEqualTo "legacy"
        WebEnvironment.bundleVersionOrNull().shouldBeNull()
        WebEnvironment.userAgentOrNull().shouldBeNull()
    }

    @Test
    fun `identifying switches the variant to web and remembers both fields`() {
        WebEnvironment.identify(bundleVersion = "abc1234", userAgent = "Mozilla/5.0 (Muma WebView)")

        WebEnvironment.uiVariant() shouldBeEqualTo "web"
        WebEnvironment.bundleVersionOrNull() shouldBeEqualTo "abc1234"
        WebEnvironment.userAgentOrNull() shouldBeEqualTo "Mozilla/5.0 (Muma WebView)"
    }

    @Test
    fun `a blank field is remembered as absent, not as an empty string`() {
        WebEnvironment.identify(bundleVersion = "  ", userAgent = "")

        WebEnvironment.bundleVersionOrNull().shouldBeNull()
        WebEnvironment.userAgentOrNull().shouldBeNull()
        // Still identified as the web UI: a build without a known version is not the same thing
        // as never having booted.
        WebEnvironment.uiVariant() shouldBeEqualTo "web"
    }

    @Test
    fun `a later identify call replaces the earlier one rather than merging with it`() {
        WebEnvironment.identify(bundleVersion = "abc1234", userAgent = "first")
        WebEnvironment.identify(bundleVersion = null, userAgent = "second")

        WebEnvironment.bundleVersionOrNull().shouldBeNull()
        WebEnvironment.userAgentOrNull() shouldBeEqualTo "second"
    }

    // --------------------------------------------------- buildEnvironmentHeader

    @Test
    fun `the legacy UI's header is exactly one line`() {
        buildEnvironmentHeader(uiVariant = "legacy", bundleVersion = null, userAgent = null) shouldBeEqualTo "UI: legacy\n"
    }

    @Test
    fun `a web report's header carries the bundle and the user agent too`() {
        val header = buildEnvironmentHeader(
            uiVariant = "web",
            bundleVersion = "abc1234",
            userAgent = "Mozilla/5.0 (Muma WebView)"
        )

        header shouldBeEqualTo "UI: web\nFrontend bundle: abc1234\nWebView UA: Mozilla/5.0 (Muma WebView)\n"
    }

    @Test
    fun `a web report without a known bundle version leaves that line out`() {
        val header = buildEnvironmentHeader(uiVariant = "web", bundleVersion = null, userAgent = "some UA")

        header shouldBeEqualTo "UI: web\nWebView UA: some UA\n"
    }
}
