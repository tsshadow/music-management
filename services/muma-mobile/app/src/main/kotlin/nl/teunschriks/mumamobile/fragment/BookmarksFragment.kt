/*
 * BookmarksFragment.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.View
import androidx.lifecycle.LiveData
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.adapters.BaseAdapter
import nl.teunschriks.mumamobile.domain.MusicDirectory
import nl.teunschriks.mumamobile.domain.MusicDirectoryEntry
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.fragment.FragmentTitle.setTitle
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.util.toastingExceptionHandler

/**
 * Lists the Bookmarks available on the server
 *
 * Bookmarks allows to save the play position of tracks, especially useful for longer tracks like
 * audio books etc.
 *
 * Therefore this fragment allows only for singular selection and playback.
 */
class BookmarksFragment : TrackCollectionFragment() {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        setTitle(this, R.string.button_bar_bookmarks)

        viewAdapter.selectionType = BaseAdapter.SelectionType.SINGLE
    }

    override fun getLiveData(
        refresh: Boolean,
        append: Boolean
    ): LiveData<List<MusicDirectoryEntry>> {
        listModel.viewModelScope.launch(
            toastingExceptionHandler()
        ) {
            swipeRefresh?.isRefreshing = true
            listModel.getBookmarks()
            swipeRefresh?.isRefreshing = false
        }
        return listModel.currentList
    }

    /**
     * Set a custom listener to perform the playing, in order to be able to restore
     * the playback position
     */
    override fun setupButtons(view: View) {
        super.setupButtons(view)

        playNowButton!!.setOnClickListener {
            playNow(getSelectedTracks())
        }
    }

    /**
     * Play the selected tracks at the bookmarked position
     */
    private fun playNow(songs: List<Track>) {
        if (songs.isNotEmpty()) {
            mediaPlayerManager.addToPlaylist(
                songs = songs,
                autoPlay = false,
                shuffle = false,
                insertionMode = MediaPlayerManager.InsertionMode.CLEAR
            )

            mediaPlayerManager.seekTo(0, songs[0].bookmarkPosition)
            mediaPlayerManager.prepare()
            mediaPlayerManager.play()
        }
    }
}
