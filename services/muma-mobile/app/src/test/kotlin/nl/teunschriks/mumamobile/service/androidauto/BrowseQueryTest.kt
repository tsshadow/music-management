/*
 * BrowseQueryTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.service.androidauto

import com.google.gson.Gson
import nl.teunschriks.mumamobile.home.TileInfo
import nl.teunschriks.mumamobile.home.toSmartParamsJson
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * A preset is the one way a quality floor reaches the car: the web writes `minQuality` into the
 * tile's params, and the car has to play it as the cluster list rather than lose it on the way,
 * which is what happened to label and festival presets before [BrowseQuery.fromTile] existed.
 */
@RunWith(RobolectricTestRunner::class)
class BrowseQueryTest {

    @Test
    fun `a tile with a quality floor plays every tier down to it`() {
        val tile = Gson().fromJson(
            """{"pageKey":"songs","genre":["Hardstyle"],"minQuality":"320","length":"short"}""",
            TileInfo::class.java
        )

        BrowseQuery.fromTile(tile).toFilters().toString() `should contain`
            """{"name":"QUALITY","value":["lossless", "320"]}"""
    }

    @Test
    fun `a tile without a floor sends no quality cluster`() {
        val tile = TileInfo(pageKey = "songs", genre = listOf("Hardstyle"))

        BrowseQuery.fromTile(tile).toFilters().toString() `should not contain` "QUALITY"
    }

    @Test
    fun `a floor this app does not know filters nothing rather than everything or an error`() {
        val tile = TileInfo(pageKey = "songs", minQuality = "hifi")

        BrowseQuery.fromTile(tile).toFilters().toString() `should not contain` "QUALITY"
    }

    @Test
    fun `the floor round-trips through the tile's own JSON`() {
        val json = TileInfo(pageKey = "songs", minQuality = "lossless").toSmartParamsJson()

        Gson().fromJson(json, TileInfo::class.java).minQuality `should be equal to` "lossless"
    }
}
