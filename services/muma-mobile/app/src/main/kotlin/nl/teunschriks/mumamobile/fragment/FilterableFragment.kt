package nl.teunschriks.mumamobile.fragment

import nl.teunschriks.mumamobile.util.LayoutType
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.view.SortOrder
import nl.teunschriks.mumamobile.view.ViewCapabilities

interface FilterableFragment {
    fun setLayoutType(newType: LayoutType) {}
    fun setOrderType(newOrder: SortOrder)
    fun setQuery(query: String?) {}
    fun setOnSetsToggle(isSets: Boolean) {}
    val isSetsMode: Boolean get() = Settings.isSetsMode
    var viewCapabilities: ViewCapabilities
}
