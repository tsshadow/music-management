package nl.teunschriks.mumamobile.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LineupTreeTest {

    // What getLineups answers with: one entry per file, and one per directory above it.
    private val lineups = listOf(
        "Defqon.1",
        "Defqon.1/2014",
        "Defqon.1/2014/RED",
        "Defqon.1/2014/BLUE",
        "Defqon.1/2025",
        "Defqon.1/2025/RED",
        "Decibel Outdoor",
        "Decibel Outdoor/2025",
        "Intents 2016"
    )

    @Test
    fun `shows only the festivals at the root`() {
        val entries = lineupLevel(lineups, path = "")

        assertEquals(listOf("Decibel Outdoor", "Defqon.1", "Intents 2016"), entries.map { it.value })
    }

    @Test
    fun `marks which entries go deeper and which open tracks`() {
        val entries = lineupLevel(lineups, path = "").associateBy { it.label }

        assertTrue(entries.getValue("Defqon.1").hasChildren)
        // A flat file from before the hierarchy has nothing below it and opens its tracks.
        assertFalse(entries.getValue("Intents 2016").hasChildren)
    }

    @Test
    fun `descends to the editions of one festival`() {
        val entries = lineupLevel(lineups, path = "Defqon.1")

        assertEquals(listOf("2014", "2025"), entries.filterNot { it.isAll }.map { it.label })
    }

    @Test
    fun `offers the level itself as the first entry once you are inside one`() {
        val entries = lineupLevel(lineups, path = "Defqon.1/2014")

        assertTrue(entries.first().isAll)
        assertEquals("Defqon.1/2014", entries.first().value)
        assertEquals(listOf("BLUE", "RED"), entries.drop(1).map { it.label })
    }

    @Test
    fun `has no all entry at the root, where it would mean the whole library`() {
        assertTrue(lineupLevel(lineups, path = "").none { it.isAll })
    }

    @Test
    fun `searching looks past the level and says where a hit lives`() {
        val entries = lineupLevel(lineups, path = "", query = "red")

        assertEquals(listOf("Defqon.1/2014/RED", "Defqon.1/2025/RED"), entries.map { it.value })
        assertEquals("Defqon.1/2014", entries.first().parent)
        assertFalse(entries.first().hasChildren)
    }

    @Test
    fun `a search matches the whole path, not just the last step`() {
        val entries = lineupLevel(lineups, path = "", query = "defqon 2014")

        assertTrue(entries.map { it.value }.contains("Defqon.1/2014"))
    }

    @Test
    fun `an unknown path lands on an empty level rather than throwing`() {
        assertTrue(lineupLevel(lineups, path = "Nope/2099").isEmpty())
    }

    @Test
    fun `the parent of a level is the step above it`() {
        assertEquals("Defqon.1", parentLineup("Defqon.1/2014"))
        assertEquals("", parentLineup("Defqon.1"))
    }
}
