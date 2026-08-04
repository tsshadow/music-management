/*
 * EntryListFragment.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.MenuItem
import android.view.View
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import kotlinx.coroutines.launch
import io.reactivex.rxjava3.disposables.CompositeDisposable
import org.koin.core.component.KoinScopeComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.NavigationGraphDirections
import nl.teunschriks.mumamobile.adapters.FolderSelectorBinder
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Artist
import nl.teunschriks.mumamobile.domain.GenericEntry
import nl.teunschriks.mumamobile.domain.Identifiable
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.ContextMenuUtil.handleContextMenu

/**
 * An extension of the MultiListFragment, with a few helper functions geared
 * towards the display of MusicDirectory.Entries.
 * @param T: The type of data which will be used (must extend GenericEntry)
 */
abstract class EntryListFragment<T : GenericEntry> :
    MultiListFragment<T>(),
    KoinScopeComponent {

    private var rxBusSubscription: CompositeDisposable = CompositeDisposable()
    private val mediaPlayerManager: MediaPlayerManager by inject()

    /**
     * Whether to show the folder selector
     */
    private fun showFolderHeader(): Boolean = listModel.showSelectFolderHeader() &&
        !listModel.isOffline() &&
        !ActiveServerProvider.shouldUseId3Tags()

    override fun onContextMenuItemSelected(menuItem: MenuItem, item: T): Boolean {
        val isArtist = (item is Artist)

        return handleContextMenu(menuItem, item, isArtist, mediaPlayerManager, this)
    }

    override fun onItemClick(item: T) {
        val action = NavigationGraphDirections.toTrackCollection(
            id = item.id,
            name = item.name,
            parentId = item.id,
            isArtist = (item is Artist)
        )

        findNavController().navigate(action)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Call a cheap function on ServerSettingsModel to make sure it is initialized by Koin,
        // because it can't be initialized from inside the callback
        serverSettingsModel.toString()

        rxBusSubscription += RxBus.musicFolderChangedEventObservable.subscribe {
            if (!listModel.isOffline()) {
                val currentSetting = listModel.activeServer
                currentSetting.musicFolderId = it.id
                viewLifecycleOwner.lifecycleScope.launch {
                    serverSettingsModel.updateItem(currentSetting)
                }
            }
            listModel.refresh(swipeRefresh!!)
        }

        viewAdapter.register(
            FolderSelectorBinder(view.context)
        )
    }

    override fun onDestroyView() {
        super.onDestroyView()
        rxBusSubscription.dispose()
    }

    /**
     * The rows shown above the list itself. Subclasses extend this rather than [defaultObserver],
     * so that whatever they add lands alongside the folder selector instead of replacing it.
     */
    internal open fun headerRows(items: List<T>): List<Identifiable> = if (showFolderHeader()) {
        listOf(folderHeader)
    } else {
        emptyList()
    }

    /**
     * What to do when the list has changed
     */
    override val defaultObserver: (List<T>) -> Unit = {
        emptyView.isVisible = it.isEmpty() && !(swipeRefresh?.isRefreshing ?: false)

        val headers = headerRows(it)
        if (headers.isEmpty()) {
            viewAdapter.submitList(it)
        } else {
            val list = mutableListOf<Identifiable>()
            list.addAll(headers)
            list.addAll(it)
            viewAdapter.submitList(list)
        }
    }

    /**
     * Get a folder header and update it on changes
     */
    private val folderHeader: FolderSelectorBinder.FolderHeader by lazy {
        val header = FolderSelectorBinder.FolderHeader(
            listModel.musicFolders.value!!,
            listModel.activeServer.musicFolderId
        )

        listModel.musicFolders.observe(
            viewLifecycleOwner
        ) {
            header.folders = it
            viewAdapter.notifyItemChanged(0)
        }

        header
    }
}
