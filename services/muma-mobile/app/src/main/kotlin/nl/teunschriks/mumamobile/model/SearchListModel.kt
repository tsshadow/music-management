/*
 * SearchListModel.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.model

import android.app.Application
import androidx.lifecycle.MutableLiveData
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.domain.SearchCriteria
import nl.teunschriks.mumamobile.domain.SearchResult
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Settings

class SearchListModel(application: Application) : GenericListModel(application) {

    var searchResult: MutableLiveData<SearchResult?> = MutableLiveData()
    var autoPlayExecuted = false

    suspend fun search(query: String): SearchResult? {
        val maxArtists = Settings.maxArtists
        val maxAlbums = Settings.maxAlbums
        val maxSongs = Settings.maxSongs

        return withContext(Dispatchers.IO) {
            val criteria = SearchCriteria(query, maxArtists, maxAlbums, maxSongs)
            val service = MusicServiceFactory.getMusicService()
            val result = service.search(criteria)

            if (result != null) searchResult.postValue(result)
            result
        }
    }

    fun trimResultLength(
        result: SearchResult,
        maxArtists: Int = Settings.defaultArtists,
        maxAlbums: Int = Settings.defaultAlbums,
        maxSongs: Int = Settings.defaultSongs
    ): SearchResult = SearchResult(
        artists = result.artists.take(maxArtists),
        albums = result.albums.take(maxAlbums),
        songs = result.songs.take(maxSongs)
    )
}
