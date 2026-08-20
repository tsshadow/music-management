/*
 * NewsModelsTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.muma

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Test

class NewsModelsTest {

    @Test
    fun `parses the snake case fields the server sends`() {
        val json = """{"id":2,"source":"nos","started_at":1787248800.0,
            "duration_ms":612000,"size_bytes":14688000}"""
        val bulletin = Gson().fromJson(json, NewsBulletin::class.java)
        assertEquals(2L, bulletin.id)
        assertEquals("nos", bulletin.source)
        assertEquals(1787248800.0, bulletin.startedAt, 0.001)
        assertEquals(612000, bulletin.durationMs)
        assertEquals(14688000L, bulletin.sizeBytes)
    }

    @Test
    fun `an empty bulletin list parses rather than throwing`() {
        val response = Gson().fromJson("""{"bulletins":[]}""", NewsBulletinsResponse::class.java)
        assertEquals(emptyList<NewsBulletin>(), response.bulletins)
    }
}
