package nl.teunschriks.mumamobile.api.muma

import com.google.gson.GsonBuilder
import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * The Muma client is wired with Gson (see MumaAPIClient), so these models must
 * carry @SerializedName for every snake_case field the backend returns.
 */
class RadioModelsTest {

    private val gson = GsonBuilder().setLenient().create()

    @Test
    fun `should parse channels response`() {
        val json = """{"channels":[{"slug":"main","name":"Radio","genre":null}]}"""
        val parsed = gson.fromJson(json, RadioChannelsResponse::class.java)
        parsed.channels.size shouldBeEqualTo 1
        parsed.channels[0].slug shouldBeEqualTo "main"
        parsed.channels[0].name shouldBeEqualTo "Radio"
        parsed.channels[0].genre shouldBeEqualTo null
    }

    @Test
    fun `should parse stations response with the stream address`() {
        val json = """{"stations":[{"slug":"slam","name":"SLAM",
            "stream_url":"https://example.com/slam.mp3","sort_order":10,"enabled":true}]}"""
        val parsed = gson.fromJson(json, RadioStationsResponse::class.java)
        parsed.stations[0].slug shouldBeEqualTo "slam"
        parsed.stations[0].streamUrl shouldBeEqualTo "https://example.com/slam.mp3"
    }

    @Test
    fun `should parse state response with snake case fields`() {
        val json = """{"server_time":1000.5,
            "channel":{"slug":"main","name":"Radio","genre":null},
            "current":{"track_id":"tr-42","title":"T","artist":"A","album":"B",
                       "cover_art":"al-7","duration_ms":215000,
                       "started_at":970.0,"ends_at":1185.0},
            "next":null}"""
        val parsed = gson.fromJson(json, RadioStateResponse::class.java)
        parsed.serverTime shouldBeEqualTo 1000.5
        parsed.current!!.trackId shouldBeEqualTo "tr-42"
        parsed.current!!.startedAt shouldBeEqualTo 970.0
        parsed.current!!.durationMs shouldBeEqualTo 215000
        parsed.current!!.coverArt shouldBeEqualTo "al-7"
        parsed.next shouldBeEqualTo null
    }

    @Test
    fun `should parse state response with an empty timeline`() {
        val json = """{"server_time":1000.0,
            "channel":{"slug":"main","name":"Radio","genre":null},
            "current":null,"next":null}"""
        val parsed = gson.fromJson(json, RadioStateResponse::class.java)
        parsed.current shouldBeEqualTo null
    }

    @Test
    fun `should parse time response`() {
        val parsed = gson.fromJson("""{"server_time":1754040000.25}""", RadioTimeResponse::class.java)
        parsed.serverTime shouldBeEqualTo 1754040000.25
    }
}
