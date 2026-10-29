package nl.teunschriks.mumamobile.api.subsonic

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.junit.Test

/** Which stored servers belong to the owner: the configured host and `muma.ownDomain`, nothing else. */
class ServerHostsTest {
    private val own = "https://music.example.org"
    private val domain = "example.org"

    @Test
    fun `the configured host is own, with any case, port, path or scheme`() {
        ServerHosts.isOwn("https://music.example.org", own, domain).shouldBeTrue()
        ServerHosts.isOwn("HTTPS://Music.Example.ORG:8443/rest/", own, domain).shouldBeTrue()
        ServerHosts.isOwn("music.example.org", own, domain).shouldBeTrue()
    }

    @Test
    fun `a subdomain and the apex of the own domain are own`() {
        ServerHosts.isOwn("https://lms.example.org", own, domain).shouldBeTrue()
        ServerHosts.isOwn("https://a.b.example.org", own, domain).shouldBeTrue()
        ServerHosts.isOwn("https://example.org", own, domain).shouldBeTrue()
    }

    @Test
    fun `an empty own domain leaves the exact host`() {
        ServerHosts.isOwn("https://music.example.org/x", own, "").shouldBeTrue()
        ServerHosts.isOwn("https://lms.example.org", own, "").shouldBeFalse()
        ServerHosts.isOwn("https://lms.example.org", own).shouldBeFalse()
    }

    @Test
    fun `a sibling on a shared suffix is not own`() {
        ServerHosts.isOwn("https://y.duckdns.org", "https://x.duckdns.org", "").shouldBeFalse()
        ServerHosts.isOwn("https://b.example.co.uk", "https://a.example.co.uk", "").shouldBeFalse()
        ServerHosts.isOwn("https://b.example.co.uk", "https://a.example.co.uk", "a.example.co.uk").shouldBeFalse()
    }

    @Test
    fun `a lookalike suffix is not own`() {
        ServerHosts.isOwn("https://example.org.evil.com", own, domain).shouldBeFalse()
        ServerHosts.isOwn("https://badexample.org", own, domain).shouldBeFalse()
        ServerHosts.isOwn("https://example.org@evil.com", own, domain).shouldBeFalse()
    }

    @Test
    fun `a host with an underscore is still read`() {
        ServerHosts.hostOf("https://my_nas.example.org") shouldBeEqualTo "my_nas.example.org"
        ServerHosts.hostOf("HTTPS://User:pw@My_NAS.Example.org:8443/rest?x=1") shouldBeEqualTo "my_nas.example.org"
        ServerHosts.isOwn("https://my_nas.example.org", own, domain).shouldBeTrue()
    }

    @Test
    fun `an empty or hostless url is never own`() {
        ServerHosts.isOwn("", own, domain).shouldBeFalse()
        ServerHosts.isOwn("https://", own, domain).shouldBeFalse()
        ServerHosts.hostOf("  ") shouldBeEqualTo ""
    }

    @Test
    fun `ip addresses match only themselves`() {
        ServerHosts.isOwn("http://10.0.0.5", "http://10.0.0.6", domain).shouldBeFalse()
        ServerHosts.isOwn("http://10.0.0.5:8080", "http://10.0.0.5", "").shouldBeTrue()
    }
}
