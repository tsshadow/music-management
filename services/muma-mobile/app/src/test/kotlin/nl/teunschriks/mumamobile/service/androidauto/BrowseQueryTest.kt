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
import org.amshove.kluent.`should be empty`
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be null`
import org.amshove.kluent.`should contain`
import org.amshove.kluent.`should not contain`
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * A preset is the one way a quality floor reaches the car: the web writes `minQuality` into the
 * tile's params, and the car has to play it as the cluster list rather than lose it on the way,
 * which is what happened to label and festival presets before [BrowseQuery.fromTile] existed.
 *
 * The same holds for the track form (issue #47): a sets preset saved with a Soort, and the car's
 * own form rows, have to reach `getSongs` as `form` -- and only ever with a value the server knows.
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

    // --- track form (issue #47) ----------------------------------------------------------------

    @Test
    fun `a sets tile with a form plays that form`() {
        val tile = Gson().fromJson(
            """{"pageKey":"sets","festival":["Defqon.1"],"length":"long","form":"liveset"}""",
            TileInfo::class.java
        )

        val query = BrowseQuery.fromTile(tile)

        query.forms `should be equal to` listOf("liveset")
        query.toFilters().toString() `should contain` """{"name":"LENGTH","value":"long"}"""
    }

    @Test
    fun `with a form one year is the filing year rather than the tag-year cluster`() {
        val tile = TileInfo(pageKey = "sets", length = "long", form = "liveset", year = listOf("2012"))

        val query = BrowseQuery.fromTile(tile)

        query.year `should be equal to` 2012
        query.toFilters().toString() `should not contain` "YEAR"
    }

    @Test
    fun `without a form the year stays the cluster`() {
        val query = BrowseQuery.fromTile(TileInfo(pageKey = "sets", length = "long", year = listOf("2012")))

        query.year.`should be null`()
        query.toFilters().toString() `should contain` """{"name":"YEAR","value":"2012"}"""
    }

    @Test
    fun `a form this app does not know is not sent`() {
        BrowseQuery.fromTile(TileInfo(pageKey = "sets", length = "long", form = "mixtape")).forms.`should be empty`()
    }

    @Test
    fun `a form on a songs tile is ignored rather than contradicting the length`() {
        BrowseQuery.fromTile(TileInfo(pageKey = "songs", length = "short", form = "liveset")).forms.`should be empty`()
    }

    @Test
    fun `the form round-trips through the tile's own JSON`() {
        val json = TileInfo(pageKey = "sets", length = "long", form = "podcast").toSmartParamsJson()

        Gson().fromJson(json, TileInfo::class.java).form `should be equal to` "podcast"
    }

    @Test
    fun `an old tile without a form reads as none`() {
        Gson().fromJson("""{"pageKey":"sets","length":"long"}""", TileInfo::class.java).form.`should be null`()
    }

    @Test
    fun `a form row of the car becomes the form parameter, and its year the filing year`() {
        val query = TagQuery("long", BrowseQuery.TAG_FORM, "liveset", year = "2019").toBrowseQuery()

        query.forms `should be equal to` listOf("liveset")
        query.year `should be equal to` 2019
        query.clusters.keys `should not contain` BrowseQuery.TAG_FORM
        query.clusters.keys `should not contain` BrowseQuery.CLUSTER_YEAR
    }

    @Test
    fun `a mangled form row narrows nothing and keeps its year as the cluster`() {
        val query = TagQuery("long", BrowseQuery.TAG_FORM, "mixtape", year = "2019").toBrowseQuery()

        query.forms.`should be empty`()
        query.year.`should be null`()
        query.clusters.keys `should not contain` BrowseQuery.TAG_FORM
        query.clusters[BrowseQuery.CLUSTER_YEAR] `should be equal to` listOf("2019")
    }

    @Test
    fun `a form row survives the media id the car hands back`() {
        val row = TagQuery("long", BrowseQuery.TAG_FORM, "podcast")

        TagQuery.parse(row.mediaId(MediaLibraryBase.MEDIA_TAG_TRACKS).split('|')) `should be equal to` row
    }
}
