/*
 * HomeCardAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.coverart.AppGenreTints
import nl.teunschriks.mumamobile.coverart.PlaylistArtKind
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.FileUtil
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject

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
    KoinComponent,
    CoroutineScope by CoroutineScope(Dispatchers.IO) {

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

    /**
     * The second line, which the grid treats differently from every other style.
     *
     * A list or a carousel card always has room for one, so it falls back to naming the card's type
     * ("Genre", "Album") when the card itself says nothing. A grid card is 56dp tall and shares that
     * space with its title, so it only spends it on something the card actually chose to say -- in
     * the shared button grid that is which section contributed the button, which is the one thing
     * the grid cannot show any other way. Everything else keeps the two-line title it has today.
     */
    private fun bindSubtitle(holder: ViewHolder, card: HomeCard, context: Context) {
        val subtitle = holder.subtitle ?: return

        if (style != CardStyle.GRID) {
            subtitle.text = card.subtitle ?: context.getString(subtitleResFor(card.type))
            return
        }

        val own = card.subtitle
        subtitle.visibility = if (own.isNullOrBlank()) View.GONE else View.VISIBLE
        subtitle.text = own.orEmpty()
        holder.title.maxLines = if (own.isNullOrBlank()) 2 else 1
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val card = items[position]
        val context = holder.itemView.context

        holder.title.text = card.title
        bindSubtitle(holder, card, context)
        holder.itemView.setOnClickListener { onClick(card) }
        holder.favorite?.visibility = if (card.isFavorite) View.VISIBLE else View.GONE
        bindMeta(holder, card)

        val longClick = onLongClick
        if (longClick == null) {
            holder.itemView.setOnLongClickListener(null)
        } else {
            holder.itemView.setOnLongClickListener { view -> longClick(view, card) }
        }

        val drawn = HomeCardArt.kindFor(card)
        if (drawn != null) {
            bindDrawnCover(holder, card, drawn)
            return
        }

        holder.image.tag = null
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

    /**
     * A cover the app draws itself, for the families that have no picture to load.
     *
     * The tint lookup can reach MuMa on its first call, so this cannot run on the main thread --
     * and the view is recycled while it does, which is what the tag guards: by the time a tile is
     * ready its holder may be showing a different card, and setting it then would put the wrong
     * cover on screen.
     */
    private fun bindDrawnCover(holder: ViewHolder, card: HomeCard, kind: PlaylistArtKind) {
        holder.image.setImageResource(defaultResourceFor(card.type))

        // Stamped here, synchronously, and not once the tile is ready: by then this holder may
        // already have been rebound, and a tag written then would mark the new card as owning the
        // old card's cover.
        val bound = card.key
        holder.image.tag = bound

        launch {
            val tint = AppGenreTints.cache.tintFor(HomeCardArt.tintNameFor(card))
            val art = HomeCardArt.tile(kind, card.title, tint)
            withContext(Dispatchers.Main) {
                if (holder.image.tag == bound) holder.image.setImageBitmap(art)
            }
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
        // A section button names itself in its title; the fallback is never reached in the grid,
        // which is the only place these appear.
        HomeCardType.SECTION -> R.string.music_library_label
    }

    private fun defaultResourceFor(type: HomeCardType): Int = when (type) {
        HomeCardType.SECTION -> R.drawable.ic_menu_playlists
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
        override fun areItemsTheSame(oldItemPosition: Int, newItemPosition: Int) = old[oldItemPosition].key == new[newItemPosition].key

        override fun areContentsTheSame(oldItemPosition: Int, newItemPosition: Int) = old[oldItemPosition] == new[newItemPosition]
    }
}
