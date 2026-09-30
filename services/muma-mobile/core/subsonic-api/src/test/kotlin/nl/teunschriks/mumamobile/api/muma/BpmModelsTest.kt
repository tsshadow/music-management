package nl.teunschriks.mumamobile.api.muma

import com.google.gson.Gson
import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeNull
import org.junit.Test

/**
 * The BPM browse answers as the car reads them (issue #140). The snake_case names are pinned
 * here: a renamed property without its `@SerializedName` would compile and silently read null,
 * which in the car is an empty tempo row or one that never continues.
 */
class BpmModelsTest {

    private val gson = Gson()

    @Test
    fun `a tracks page reads its paths, tempo and where the next page starts`() {
        val page = gson.fromJson(
            """{"bpm_from": 148, "bpm_to": 152, "center": 150, "tolerance": 2, "total": 250,
               "offset": 0, "next_offset": 100,
               "tracks": [{"id": 7, "title": "T", "artist": "A", "library_path": "EPs/x.mp3",
                           "bpm": 150.02, "bpm_source": "measured", "bpm_confidence": "high"}]}""",
            MumaBpmTracks::class.java
        )

        page.total shouldBeEqualTo 250
        page.nextOffset shouldBeEqualTo 100
        page.tracks.single().libraryPath shouldBeEqualTo "EPs/x.mp3"
        page.tracks.single().bpm shouldBeEqualTo 150.02
        page.tracks.single().bpmConfidence shouldBeEqualTo "high"
    }

    @Test
    fun `the last page says so with a null next offset`() {
        gson.fromJson("""{"total": 1, "offset": 0, "next_offset": null, "tracks": []}""", MumaBpmTracks::class.java)
            .nextOffset.shouldBeNull()
    }

    @Test
    fun `the histogram reads its bins and the default tolerance`() {
        val histogram = gson.fromJson(
            """{"bins": [{"bpm": 150, "count": 12, "high": 10, "medium": 2, "low": 0}],
               "genres": [], "default_tolerance": 2.0, "summary": {}}""",
            MumaBpmHistogram::class.java
        )

        histogram.bins.single().bpm shouldBeEqualTo 150
        histogram.bins.single().count shouldBeEqualTo 12
        histogram.defaultTolerance shouldBeEqualTo 2.0
    }
}
