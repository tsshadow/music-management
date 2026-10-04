package nl.teunschriks.mumamobile.imageloader

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.amshove.kluent.shouldNotContain
import org.junit.Test

/**
 * Bug report 150: the web player passed a signed getCoverArt URL where a cover-art id belongs,
 * and the app sent it nested inside a new getCoverArt request.
 */
class CoverArtIdTest {

    private val signedUrl = "https://muma.example.org/rest/getCoverArt?id=art-824661-1786979739&size=512" +
        "&u=user&t=0123456789abcdef&s=salt42&v=1.16.1&c=muma"

    @Test
    fun `a plain id comes back unchanged`() {
        coverArtIdOf("art-824661-1786979739") shouldBeEqualTo "art-824661-1786979739"
        coverArtIdOf("al-12") shouldBeEqualTo "al-12"
    }

    @Test
    fun `nothing is no id`() {
        coverArtIdOf(null).shouldBeNull()
        coverArtIdOf("").shouldBeNull()
        coverArtIdOf("   ").shouldBeNull()
    }

    @Test
    fun `a signed getCoverArt URL gives its id`() {
        coverArtIdOf(signedUrl) shouldBeEqualTo "art-824661-1786979739"
    }

    @Test
    fun `the view suffix and an encoded id are understood`() {
        coverArtIdOf("http://lms:5082/rest/getCoverArt.view?u=user&id=al%2D7&size=300") shouldBeEqualTo "al-7"
    }

    @Test
    fun `a URL to anything else is not a cover-art id`() {
        coverArtIdOf("https://muma.example.org/images/spotify-fallback.svg").shouldBeNull()
        coverArtIdOf("https://muma.example.org/rest/stream?id=tr-1").shouldBeNull()
    }

    @Test
    fun `a getCoverArt URL without an id gives nothing`() {
        coverArtIdOf("https://muma.example.org/rest/getCoverArt?size=512").shouldBeNull()
    }

    @Test
    fun `redaction removes the token, the salt and the user name`() {
        val redacted = redactCredentials(signedUrl)!!

        redacted shouldBeEqualTo "https://muma.example.org/rest/getCoverArt?id=art-824661-1786979739&size=512" +
            "&u=REDACTED&t=REDACTED&s=REDACTED&v=1.16.1&c=muma"
    }

    @Test
    fun `redaction also reaches a percent-encoded nested URL`() {
        val nested = "content://x/https%3A%2F%2Fm%2Frest%2FgetCoverArt%3Fid%3Dal-1%26t%3Dtok%26s%3Dsalt%26u%3Dteun|key"

        val redacted = redactCredentials(nested)!!

        redacted shouldNotContain "tok"
        redacted shouldNotContain "salt"
        redacted shouldNotContain "user"
        redacted shouldBeEqualTo "content://x/https%3A%2F%2Fm%2Frest%2FgetCoverArt%3Fid%3Dal-1%26t%3DREDACTED%26s%3DREDACTED%26u%3DREDACTED|key"
    }

    @Test
    fun `redaction leaves a plain id alone`() {
        redactCredentials("art-824661-1786979739") shouldBeEqualTo "art-824661-1786979739"
        redactCredentials(null).shouldBeNull()
    }
}
