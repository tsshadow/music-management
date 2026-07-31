package org.moire.ultrasonic.fragment

import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

// Robolectric only because Bundle is an Android type; nothing here touches a real device.
@RunWith(RobolectricTestRunner::class)
@Config(application = org.moire.ultrasonic.app.UApp::class, manifest = Config.NONE)
class LibraryPagerAdapterTest {

    @Test
    fun `has one page per library category`() {
        LibraryPagerAdapter.PAGE_COUNT `should be equal to` 5
    }

    @Test
    fun `every page has a distinct title`() {
        val titles = (0 until LibraryPagerAdapter.PAGE_COUNT).map {
            LibraryPagerAdapter.titleResFor(it)
        }

        titles.distinct().size `should be equal to` LibraryPagerAdapter.PAGE_COUNT
    }

    @Test
    fun `pages written as navigation destinations get an arguments bundle`() {
        // ArtistListFragment and AlbumListFragment read navArgs(), which throws when the arguments
        // bundle is missing. Without this the Library tab would crash on those two pages.
        val artistArgs = LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_ARTISTS)!!
        val albumArgs = LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_ALBUMS)!!

        artistArgs.keySet() `should be equal to` setOf("refresh", "title", "id")
        albumArgs.containsKey("type") `should be equal to` true
        albumArgs.getInt("size") `should be equal to` 500
    }

    @Test
    fun `pages that take no navigation arguments get no bundle`() {
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_GENRES).shouldBeNull()
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_DYNAMIC_PLAYLISTS)
            .shouldBeNull()
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_STATIC_PLAYLISTS)
            .shouldBeNull()
    }
}
