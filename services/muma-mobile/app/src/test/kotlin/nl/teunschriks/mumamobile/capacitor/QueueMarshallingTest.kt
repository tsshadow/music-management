package nl.teunschriks.mumamobile.capacitor

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `setQueue` is where the two codebases actually touch: the web player owns the queue and the
 * native service holds it, and the only thing keeping them agreed is that index `n` of the request
 * is index `n` of the playlist. These tests are on `org.json`, so they need Robolectric -- the
 * stubbed `org.json` of a plain JVM unit test throws on every call.
 */
@RunWith(RobolectricTestRunner::class)
class QueueMarshallingTest {

    private fun track(id: String, title: String? = null): JSONObject = JSONObject().apply {
        put("id", id)
        if (title != null) put("title", title)
    }

    @Test
    fun `the order of the request is the order of the queue`() {
        val json = JSONArray().apply {
            put(track("c"))
            put(track("a"))
            put(track("b"))
        }

        queueTracksOf(json).map { it.id } shouldBeEqualTo listOf("c", "a", "b")
        queueTracksOf(json).toTracks(serverId = 7).map { it.id } shouldBeEqualTo listOf("c", "a", "b")
    }

    @Test
    fun `every field the notification shows survives the crossing`() {
        val json = JSONObject().apply {
            put("id", "42")
            put("title", "Trance Energy 2004")
            put("artist", "Marco V")
            put("album", "Trance Energy")
            put("coverArt", "al-42")
            put("duration", 4711)
        }

        val parsed = queueTrackOf(json)!!
        parsed.title shouldBeEqualTo "Trance Energy 2004"
        parsed.artist shouldBeEqualTo "Marco V"
        parsed.album shouldBeEqualTo "Trance Energy"
        parsed.coverArt shouldBeEqualTo "al-42"
        parsed.duration shouldBeEqualTo 4711

        val domain = parsed.toTrack(serverId = 3)
        domain.serverId shouldBeEqualTo 3
        domain.coverArt shouldBeEqualTo "al-42"
        domain.duration shouldBeEqualTo 4711
        domain.isDirectory shouldBeEqualTo false
    }

    /**
     * Bug report 150. An older web bundle sends a signed getCoverArt URL as `artworkUrl`. Kept as
     * the cover-art id, the image loader sent it as the `id` of a new getCoverArt request, and
     * the track kept the user's token. The id inside the URL is what the track must hold.
     */
    @Test
    fun `a signed artwork URL becomes the cover-art id inside it`() {
        val json = JSONObject().apply {
            put("id", "42")
            put(
                "artworkUrl",
                "https://muma.example.org/rest/getCoverArt?id=art-824661-1786979739&size=512&u=user&t=abc&s=salt&v=1"
            )
        }

        val domain = queueTrackOf(json)!!.toTrack(serverId = 3)

        domain.coverArt shouldBeEqualTo "art-824661-1786979739"
    }

    @Test
    fun `the cover-art id wins over the artwork URL`() {
        val json = JSONObject().apply {
            put("id", "42")
            put("coverArt", "al-7")
            put("artworkUrl", "https://muma.example.org/rest/getCoverArt?id=al-8&t=abc&s=salt")
        }

        queueTrackOf(json)!!.toTrack(serverId = 3).coverArt shouldBeEqualTo "al-7"
    }

    /** The web player's fallback picture is a URL, but no cover-art id: the track gets none. */
    @Test
    fun `an artwork URL that is not getCoverArt gives no cover art`() {
        val json = JSONObject().apply {
            put("id", "42")
            put("artworkUrl", "https://muma.example.org/images/spotify-fallback.svg")
        }

        queueTrackOf(json)!!.toTrack(serverId = 3).coverArt.shouldBeNull()
    }

    @Test
    fun `a track with only an id is still playable`() {
        val parsed = queueTrackOf(track("42"))!!
        parsed.id shouldBeEqualTo "42"
        parsed.title.shouldBeNull()
        parsed.duration.shouldBeNull()
    }

    /**
     * A queue with one unusable row still plays. Rejecting the whole call would leave the user
     * with silence over a row the server sent without an id.
     */
    @Test
    fun `an entry without an id is dropped rather than fatal`() {
        val json = JSONArray().apply {
            put(track("a"))
            put(JSONObject().put("title", "nameless"))
            put(track("b"))
        }

        queueTracksOf(json).map { it.id } shouldBeEqualTo listOf("a", "b")
    }

    @Test
    fun `no tracks at all is an empty queue, not an exception`() {
        queueTracksOf(null) shouldBeEqualTo emptyList()
        queueTracksOf(JSONArray()) shouldBeEqualTo emptyList()
    }

    @Test
    fun `an explicit null is not a value`() {
        val json = JSONObject().apply {
            put("id", "1")
            put("title", JSONObject.NULL)
            put("duration", JSONObject.NULL)
        }

        val parsed = queueTrackOf(json)!!
        parsed.title.shouldBeNull()
        parsed.duration.shouldBeNull()
    }
}
