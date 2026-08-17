/*
 * HomeCardAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.FileUtil

/**
 * The one and only home screen card component. Adding a new section means producing a new
 * [HomeSection]; it never means writing another adapter.
 */
class HomeCardAdapter(
    private val style: CardStyle,
    private val onClick: (HomeCard) -> Unit,
    /** Only the screens that offer a context menu pass this; the view it gets is the card. */
    private val onLongClick: ((View, HomeCard) -> Boolean)? = null
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

        /** Grid cards only; the carousel layout has no room for it. */
        val favorite: ImageView? = view.findViewById(R.id.card_favorite)

        /** List rows only: the duration, and the five stars beneath it. */
        val meta: TextView? = view.findViewById(R.id.card_meta)
        val rating: View? = view.findViewById(R.id.card_rating)
        val stars: List<ImageView> = if (rating == null) {
            emptyList()
        } else {
            listOf(
                view.findViewById(R.id.card_star_1),
                view.findViewById(R.id.card_star_2),
                view.findViewById(R.id.card_star_3),
                view.findViewById(R.id.card_star_4),
                view.findViewById(R.id.card_star_5)
            )
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val layout = when (style) {
            CardStyle.GRID -> R.layout.home_card_grid
            CardStyle.CAROUSEL -> R.layout.home_card_carousel
            CardStyle.LIST -> R.layout.home_card_list
            CardStyle.BANNER -> R.layout.home_card_banner
        }

        return ViewHolder(LayoutInflater.from(parent.context).inflate(layout, parent, false))
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val card = items[position]
        val context = holder.itemView.context

        holder.title.text = card.title
        holder.subtitle?.text = card.subtitle ?: context.getString(subtitleResFor(card.type))
        holder.itemView.setOnClickListener { onClick(card) }
        holder.favorite?.visibility = if (card.isFavorite) View.VISIBLE else View.GONE
        bindMeta(holder, card)

        val longClick = onLongClick
        if (longClick == null) {
            holder.itemView.setOnLongClickListener(null)
        } else {
            holder.itemView.setOnLongClickListener { view -> longClick(view, card) }
        }

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
     * The duration and the stars, on the styles that have room for them.
     *
     * Views are recycled, so every branch here has to say what it wants: leaving the stars alone
     * when a card is unrated would show the previous row's rating.
     */
    private fun bindMeta(holder: ViewHolder, card: HomeCard) {
        holder.meta?.let {
            it.text = card.meta.orEmpty()
            it.visibility = if (card.meta.isNullOrBlank()) View.GONE else View.VISIBLE
        }

        val rating = holder.rating ?: return
        val stars = card.rating

        if (stars == null || stars <= 0) {
            rating.visibility = View.GONE
            return
        }

        rating.visibility = View.VISIBLE
        holder.stars.forEachIndexed { index, star ->
            star.setImageResource(
                if (index < stars) R.drawable.ic_star_full else R.drawable.ic_star_hollow
            )
        }
    }

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
        HomeCardType.PODCAST -> R.string.library_tab_podcasts
        HomeCardType.LINEUP -> R.string.library_tab_lineups
        HomeCardType.RATING -> R.string.library_tab_ratings
        HomeCardType.TRACK -> R.string.main_songs
        // A memory card always sets its own subtitle (the track count); this is only the fallback.
        HomeCardType.MEMORY -> R.string.home_memories
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
