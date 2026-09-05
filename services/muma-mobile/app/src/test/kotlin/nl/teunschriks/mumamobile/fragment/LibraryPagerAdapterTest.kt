package nl.teunschriks.mumamobile.fragment

import nl.teunschriks.mumamobile.home.LibraryMode
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.shouldBeNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

// Robolectric only because Bundle is an Android type; nothing here touches a real device.
@RunWith(RobolectricTestRunner::class)
@Config(application = nl.teunschriks.mumamobile.app.UApp::class, manifest = Config.NONE)
class LibraryPagerAdapterTest {

    @Test
    fun `has one page per library category`() {
        LibraryPagerAdapter.ALL_PAGES.size `should be equal to` 12
    }

    @Test
    fun `every page has a distinct title`() {
        val titles = LibraryPagerAdapter.ALL_PAGES.map { LibraryPagerAdapter.titleResFor(it) }

        titles.distinct().size `should be equal to` LibraryPagerAdapter.ALL_PAGES.size
    }

    @Test
    fun `song mode drops the pages that only hold recordings`() {
        // Mirrors COLLECTION_MODES in the web UI: the tagger writes no FESTIVAL or PODCAST tag
        // below ten minutes, so both grids are empty by construction in song mode.
        val pages = LibraryPagerAdapter.pagesFor(LibraryMode.SONGS)

        pages.contains(LibraryPagerAdapter.PAGE_FESTIVALS) `should be equal to` false
        pages.contains(LibraryPagerAdapter.PAGE_PODCASTS) `should be equal to` false
        pages.contains(LibraryPagerAdapter.PAGE_LABELS) `should be equal to` true
        pages.contains(LibraryPagerAdapter.PAGE_LINEUPS) `should be equal to` true
    }

    @Test
    fun `sets mode drops the pages that describe releases`() {
        val pages = LibraryPagerAdapter.pagesFor(LibraryMode.SETS)

        pages.contains(LibraryPagerAdapter.PAGE_LABELS) `should be equal to` false
        pages.contains(LibraryPagerAdapter.PAGE_LINEUPS) `should be equal to` false
        pages.contains(LibraryPagerAdapter.PAGE_FESTIVALS) `should be equal to` true
        pages.contains(LibraryPagerAdapter.PAGE_PODCASTS) `should be equal to` true
    }

    @Test
    fun `a page that is not a browse category shows in both modes`() {
        // Artists, albums, playlists and memories have no mode of their own; dropping one of them
        // by accident would take a whole screen off the tab strip.
        val both = LibraryPagerAdapter.pagesFor(LibraryMode.SONGS)
            .intersect(LibraryPagerAdapter.pagesFor(LibraryMode.SETS).toSet())

        both `should be equal to` setOf(
            LibraryPagerAdapter.PAGE_DYNAMIC_PLAYLISTS,
            LibraryPagerAdapter.PAGE_GENRES,
            LibraryPagerAdapter.PAGE_ARTISTS,
            LibraryPagerAdapter.PAGE_ALBUMS,
            LibraryPagerAdapter.PAGE_YEARS,
            LibraryPagerAdapter.PAGE_RATINGS,
            LibraryPagerAdapter.PAGE_STATIC_PLAYLISTS,
            LibraryPagerAdapter.PAGE_MEMORIES
        )
    }

    @Test
    fun `every page shows in at least one mode`() {
        val shown = LibraryPagerAdapter.pagesFor(LibraryMode.SONGS) +
            LibraryPagerAdapter.pagesFor(LibraryMode.SETS)

        shown.toSet() `should be equal to` LibraryPagerAdapter.ALL_PAGES.toSet()
    }

    @Test
    fun `both modes keep the pages in tab order`() {
        LibraryMode.entries.forEach { mode ->
            val pages = LibraryPagerAdapter.pagesFor(mode)

            pages `should be equal to` LibraryPagerAdapter.ALL_PAGES.filter { it in pages }
        }
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
    fun `browse pages are told which category to show`() {
        // All seven browse pages share one fragment, so the category is the only thing that
        // distinguishes them; a missing one would silently render genres seven times.
        val categories = listOf(
            LibraryPagerAdapter.PAGE_GENRES,
            LibraryPagerAdapter.PAGE_LABELS,
            LibraryPagerAdapter.PAGE_YEARS,
            LibraryPagerAdapter.PAGE_FESTIVALS,
            LibraryPagerAdapter.PAGE_PODCASTS,
            LibraryPagerAdapter.PAGE_LINEUPS,
            LibraryPagerAdapter.PAGE_RATINGS
        ).map { LibraryPagerAdapter.argumentsForPage(it)!!.getString("browseCategory") }

        categories `should be equal to` listOf(
            "GENRES",
            "LABELS",
            "YEARS",
            "FESTIVALS",
            "PODCASTS",
            "LINEUPS",
            "RATINGS"
        )
    }

    @Test
    fun `pages that need nothing get no bundle`() {
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_DYNAMIC_PLAYLISTS)
            .shouldBeNull()
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_STATIC_PLAYLISTS)
            .shouldBeNull()

        // Memories is its own screen rather than a browse category, so it reads no arguments.
        LibraryPagerAdapter.argumentsForPage(LibraryPagerAdapter.PAGE_MEMORIES)
            .shouldBeNull()
    }
}
