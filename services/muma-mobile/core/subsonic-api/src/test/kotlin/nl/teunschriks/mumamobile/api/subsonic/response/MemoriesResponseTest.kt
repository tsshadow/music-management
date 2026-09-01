package nl.teunschriks.mumamobile.api.subsonic.response

import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Unit test for [MemoriesResponse].
 *
 * Deserialises with the production mapper rather than a hand-rolled one, so that the root
 * unwrapping and the single-value-as-array coercion this response relies on are actually exercised.
 */
class MemoriesResponseTest {

    private val mapper = SubsonicAPIClient.jacksonMapper

    private fun parse(json: String) = mapper.readValue(json, MemoriesResponse::class.java)

    @Test
    fun `parses both groups with their kind, exactness and age`() {
        val response = parse(
            """
            {
              "subsonic-response": {
                "status": "ok",
                "version": "1.16.1",
                "memories": {
                  "memory": [
                    {
                      "kind": "release",
                      "year": 2018,
                      "yearsAgo": 8,
                      "exact": true,
                      "songCount": 2,
                      "song": [
                        { "id": "1", "title": "First" },
                        { "id": "2", "title": "Second" }
                      ]
                    },
                    {
                      "kind": "release",
                      "year": 2015,
                      "yearsAgo": 11,
                      "exact": false,
                      "songCount": 1,
                      "song": [ { "id": "3", "title": "Third" } ]
                    }
                  ]
                }
              }
            }
            """.trimIndent()
        )

        response.memoriesList.size `should be equal to` 2

        val newest = response.memoriesList[0]
        newest.kind `should be equal to` "release"
        newest.year `should be equal to` 2018
        newest.yearsAgo `should be equal to` 8
        newest.exact `should be equal to` true
        newest.songCount `should be equal to` 2
        newest.songs.map { it.id } `should be equal to` listOf("1", "2")

        response.memoriesList[1].exact `should be equal to` false
    }

    @Test
    fun `an empty memories node is a valid, empty answer`() {
        val response = parse(
            """
            {
              "subsonic-response": {
                "status": "ok",
                "version": "1.16.1",
                "memories": {}
              }
            }
            """.trimIndent()
        )

        response.status `should be equal to` SubsonicResponse.Status.OK
        response.memoriesList.size `should be equal to` 0
    }

    @Test
    fun `a lone group and a lone song still arrive as lists`() {
        val response = parse(
            """
            {
              "subsonic-response": {
                "status": "ok",
                "version": "1.16.1",
                "memories": {
                  "memory": {
                    "kind": "release",
                    "year": 2018,
                    "yearsAgo": 8,
                    "exact": true,
                    "songCount": 1,
                    "song": { "id": "1", "title": "Only" }
                  }
                }
              }
            }
            """.trimIndent()
        )

        response.memoriesList.size `should be equal to` 1
        response.memoriesList[0].songs.map { it.id } `should be equal to` listOf("1")
    }
}
