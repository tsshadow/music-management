/*
 * HomeCardAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.home

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import org.moire.ultrasonic.R
import org.moire.ultrasonic.subsonic.ImageLoaderProvider
import org.moire.ultrasonic.util.FileUtil

/**
 * The one and only home screen card component. Adding a new section means producing a new
 * [HomeSection]; it never means writing another adapter.
 */
class HomeCardAdapter(
    private val style: CardStyle,
    private val onClick: (HomeCard) -> Unit
) : RecyclerView.Adapter<HomeCardAdapter.ViewHolder>(),
    KoinComponent {

    private val imageLoaderProvider: ImageLoaderProvider by inject()

    var items: List<HomeCard> = emptyList()
        set(value) {
            val diff = DiffUtil.calculateDiff(Diff(field, value))
            field = value
            diff.dispatchUpdatesTo(this)
        }

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.card_title)
        val subtitle: TextView? = view.findViewById(R.id.card_subtitle)
        val image: ImageView = view.findViewById(R.id.card_image)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val layout = when (style) {
            CardStyle.GRID -> R.layout.home_card_grid
            CardStyle.CAROUSEL -> R.layout.home_card_carousel
        }

        return ViewHolder(LayoutInflater.from(parent.context).inflate(layout, parent, false))
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val card = items[position]
        val context = holder.itemView.context

        holder.title.text = card.title
        holder.subtitle?.text = card.subtitle ?: context.getString(subtitleResFor(card.type))
        holder.itemView.setOnClickListener { onClick(card) }

        imageLoaderProvider.executeOn {
            it.loadImage(
                holder.image,
                card.coverArtId,
                cacheKeyFor(card),
                true,
                0,
                defaultResourceFor(card.type)
            )
        }
    }

    override fun getItemCount() = items.size

    /**
     * The on-disk cache key. Artist art is keyed the way the rest of the app keys it, so a picture
     * fetched here is reused elsewhere instead of being downloaded again under a key nobody reads.
     */
    private fun cacheKeyFor(card: HomeCard): String = when (card.type) {
        HomeCardType.ARTIST -> FileUtil.getArtistArtKey(card.title, true)
        else -> card.title
    }

    private fun subtitleResFor(type: HomeCardType): Int = when (type) {
        HomeCardType.ALBUM -> R.string.common_album
        HomeCardType.ARTIST -> R.string.common_artist
        HomeCardType.LABEL -> R.string.home_card_label
        HomeCardType.GENRE -> R.string.home_card_genre
        HomeCardType.YEAR -> R.string.library_tab_years
        HomeCardType.FESTIVAL -> R.string.library_tab_festivals
        HomeCardType.LINEUP -> R.string.library_tab_lineups
        HomeCardType.RATING -> R.string.library_tab_ratings
        HomeCardType.TRACK -> R.string.main_songs
        HomeCardType.DYNAMIC_PLAYLIST, HomeCardType.STATIC_PLAYLIST -> R.string.playlist_label
    }

    private fun defaultResourceFor(type: HomeCardType): Int = when (type) {
        HomeCardType.ALBUM -> R.drawable.unknown_album
        HomeCardType.ARTIST -> R.drawable.ic_contact_picture
        HomeCardType.TRACK -> R.drawable.baseline_music_note_24
        else -> R.drawable.ic_menu_playlists
    }

    private class Diff(
        private val old: List<HomeCard>,
        private val new: List<HomeCard>
    ) : DiffUtil.Callback() {
        override fun getOldListSize() = old.size
        override fun getNewListSize() = new.size
        override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int) =
            old[oldItemPosition].key == new[newItemPosition].key

        override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int) =
            old[oldItemPosition] == new[newItemPosition]
    }
}
