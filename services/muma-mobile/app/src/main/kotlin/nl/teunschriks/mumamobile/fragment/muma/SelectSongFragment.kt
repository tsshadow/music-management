package nl.teunschriks.mumamobile.fragment.muma

import android.os.Bundle
import android.view.View
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.fragment.FilterableFragment
import nl.teunschriks.mumamobile.fragment.FragmentTitle.setTitle
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.view.SortOrder
import nl.teunschriks.mumamobile.view.ViewCapabilities

/**
 * Fragment for selecting or saving tile presets for regular songs and livesets.
 * Allows filtering by genre, year, rating, sort method, and optionally label.
 * Search results or saved tiles navigate to a TrackCollection.
 */
class SelectSongFragment :
    SelectFragment(),
    FilterableFragment {
    override var pageKey = "song"
    override var defaultLength = if (Settings.isSetsMode) "long" else "short"
    override var filterModalType = FilterModalType.SONG

    override var viewCapabilities: ViewCapabilities = ViewCapabilities(
        supportsGrid = false,
        supportsSetsToggle = true,
        supportedSortOrders = emptyList()
    )

    override val isSetsMode: Boolean get() = Settings.isSetsMode

    override fun setOnSetsToggle(isSets: Boolean) {
        if (isSets && pageKey == "liveset") return
        if (!isSets && pageKey == "song") return

        if (isSets) {
            pageKey = "liveset"
            defaultLength = "long"
            filterModalType = FilterModalType.LIVESET
            setTitle(this, R.string.main_livesets_title)
        } else {
            pageKey = "song"
            defaultLength = "short"
            filterModalType = FilterModalType.SONG
            setTitle(this, R.string.main_songs_title)
        }
        // Reload tiles and refresh UI
        updateBrandColors()
        loadTilesOrDefaults()
        populateTiles()
        load(false)
    }

    override fun setOrderType(newOrder: SortOrder) {
        // Tiles have their own sort methods, so we don't need to do anything here
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        if (Settings.isSetsMode) {
            pageKey = "liveset"
            defaultLength = "long"
            filterModalType = FilterModalType.LIVESET
        }
        super.onViewCreated(view, savedInstanceState)
    }

    override fun setTitle() {
        if (pageKey == "song") {
            setTitle(this, R.string.main_songs_title)
        } else {
            setTitle(this, R.string.main_livesets_title)
        }
    }

    /**
     * Plain genre tiles are redundant now that genres are browsable, so the defaults are
     * combinations the genre list can't express: a genre plus a year window. Years are
     * enumerated because the server matches YEAR values as exact clusters, not ranges.
     */
    override fun defaultTileSet(): MutableList<TileInfo> = mutableListOf(
        TileInfo(
            title = "Hardstyle Classics",
            genre = listOf("Mainstream Hardstyle"),
            year = years(2009, 2017),
            length = defaultLength,
            sortMethod = "Random",
            favorite = true
        ),
        TileInfo(
            title = "Millennium Hardcore",
            genre = listOf("Mainstream Hardcore"),
            year = years(2010, 2015),
            length = defaultLength,
            sortMethod = "Random",
            favorite = true
        ),
        TileInfo(
            title = "Early Uptempo",
            genre = listOf("Uptempo Hardcore"),
            year = years(2012, 2017),
            length = defaultLength,
            sortMethod = "Random",
            favorite = true
        )
    )

    private fun years(from: Int, to: Int): List<String> = (from..to).map(Int::toString)
}
