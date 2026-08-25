/*
 * ArtistHeaderBinder.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.adapters

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import com.drakeet.multitype.ItemViewBinder
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Settings

/**
 * The header at the top of an artist page: the artist image, the name, and a short overview of
 * the discography below the list of albums that follows it.
 */
class ArtistHeaderBinder(
    private val onPlayAll: () -> Unit,
    private val onShowAllTracks: () -> Unit = {}
) : ItemViewBinder<ArtistHeader, ArtistHeaderBinder.ViewHolder>(),
    KoinComponent {

    override fun onCreateViewHolder(inflater: LayoutInflater, parent: ViewGroup): ViewHolder = ViewHolder(inflater.inflate(R.layout.list_header_artist_detail, parent, false))

    override fun onBindViewHolder(holder: ViewHolder, item: ArtistHeader) {
        holder.title.text = item.name
        holder.setOrHide(holder.subtitle, item.subtitle)
        holder.setOrHide(holder.years, item.years)
        holder.setOrHide(holder.genres, item.genres)
        holder.playAll.setOnClickListener { onPlayAll() }
        holder.allTracks.setOnClickListener { onShowAllTracks() }

        if (!showArtistPicture()) {
            holder.coverArt.isVisible = false
            return
        }

        holder.coverArt.isVisible = true
        val imageLoaderProvider: ImageLoaderProvider by inject()
        imageLoaderProvider.executeOn {
            it.loadImage(
                view = holder.coverArt,
                id = item.coverArtId,
                key = FileUtil.getArtistArtKey(item.name, false),
                // The non-large key is the one ImageLoader.cacheArtistPicture writes, so the
                // header reuses the artist art the app already has - including offline, where a
                // large-key request would find nothing and fall back to the silhouette.
                large = false,
                size = 0,
                defaultResourceId = R.drawable.ic_contact_picture
            )
        }
    }

    /** Same rule as the artist list: no ID3 tags means no artist pictures to show. */
    private fun showArtistPicture(): Boolean = ActiveServerProvider.shouldUseId3Tags() && Settings.shouldShowArtistPicture

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val coverArt: ImageView = view.findViewById(R.id.artist_image)
        val title: TextView = view.findViewById(R.id.artist_title)
        val subtitle: TextView = view.findViewById(R.id.artist_subtitle)
        val years: TextView = view.findViewById(R.id.artist_years)
        val genres: TextView = view.findViewById(R.id.artist_genres)
        val playAll: View = view.findViewById(R.id.artist_play_all)
        val allTracks: View = view.findViewById(R.id.artist_all_tracks)

        /**
         * Holders are recycled, so a line has to be cleared as explicitly as it is filled -
         * otherwise the previous artist's genres survive underneath one that has none.
         */
        fun setOrHide(view: TextView, text: String?) {
            view.text = text
            view.isVisible = text != null
        }
    }
}
