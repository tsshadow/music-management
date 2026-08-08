/*
 * MusicDirectoryChildArtistsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.subsonic.models

import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.module.kotlin.registerKotlinModule
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * The server splits "Headhunterz, Wildstylez" into entities and sends both; a song that only
 * carries the joined display string has to keep working, so every new field defaults to empty.
 */
class MusicDirectoryChildArtistsTest {

    private val mapper = ObjectMapper()
        .registerKotlinModule()
        .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)

    @Test
    fun `a collaboration carries one entry per artist`() {
        val json = """
            {
              "id": "1",
              "artist": "Headhunterz, Wildstylez",
              "artistId": "ar-1",
              "artists": [
                {"id": "ar-1", "name": "Headhunterz"},
                {"id": "ar-2", "name": "Wildstylez"}
              ],
              "moods": ["energetic"],
              "labels": ["Scantraxx"]
            }
        """.trimIndent()

        val child = mapper.readValue(json, MusicDirectoryChild::class.java)

        child.artists.size `should be equal to` 2
        child.artists[1].id `should be equal to` "ar-2"
        child.artists[1].name `should be equal to` "Wildstylez"
        child.moods `should be equal to` listOf("energetic")
        child.labels `should be equal to` listOf("Scantraxx")
    }

    @Test
    fun `a song from a server that sends none of it stays readable`() {
        val child = mapper.readValue("""{"id": "1", "artist": "Deadmau5"}""", MusicDirectoryChild::class.java)

        child.artists `should be equal to` emptyList()
        child.moods `should be equal to` emptyList()
        child.labels `should be equal to` emptyList()
    }
}
