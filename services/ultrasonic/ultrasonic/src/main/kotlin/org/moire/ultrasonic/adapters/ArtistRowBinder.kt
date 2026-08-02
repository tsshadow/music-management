/*
 * ArtistRowBinder.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.adapters

import android.content.Context
import android.view.LayoutInflater
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.RelativeLayout
import android.widget.TextView
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import com.drakeet.multitype.ItemViewBinder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import org.moire.ultrasonic.R
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.domain.Artist
import org.moire.ultrasonic.domain.ArtistOrIndex
import org.moire.ultrasonic.domain.Identifiable
import org.moire.ultrasonic.subsonic.ImageLoaderProvider
import org.moire.ultrasonic.util.FileUtil
import org.moire.ultrasonic.util.Settings
import org.moire.ultrasonic.util.Util

/**
 * "12 albums · 143 tracks", leaving out whatever the server did not report. Folder indexes carry
 * neither count, so they get no subtitle at all.
 */
fun artistSubtitle(item: ArtistOrIndex, context: Context): String? {
    if (item !is Artist) return null

    return artistSubtitleOf(item.albumCount, item.songCount, context)
}

/**
 * The same wording from raw counts, for callers that derive the numbers themselves rather than
 * reading them off an [Artist] - the artist page counts the discography it just loaded when the
 * server never reported the totals.
 */
fun artistSubtitleOf(albumCount: Long?, songCount: Long?, context: Context): String? {
    val resources = context.resources
    val parts = mutableListOf<String>()
    albumCount?.takeIf { it > 0 }?.let {
        parts += resources.getQuantityString(R.plurals.select_artist_subtitle_albums, it.toInt(), it)
    }
    songCount?.takeIf { it > 0 }?.let {
        parts += resources.getQuantityString(R.plurals.select_artist_subtitle_tracks, it.toInt(), it)
    }

    return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
}

/**
 * Creates a Row in a RecyclerView which contains the details of an Artist
 *
 * @param enableSections Whether to show the A/B/C fast-scroll section rail. Only meaningful when
 * the list is in alphabetical order; the caller is responsible for turning it off for any other
 * sort, where the per-row letter would be noise rather than a useful index.
 */
class ArtistRowBinder(
    val onItemClick: (ArtistOrIndex) -> Unit,
    val onContextMenuClick: (MenuItem, ArtistOrIndex) -> Boolean,
    var enableSections: Boolean = true
) : ItemViewBinder<ArtistOrIndex, ArtistRowBinder.ViewHolder>(),
    KoinComponent,
    Utils.SectionedBinder {

    val layout = R.layout.list_item_artist
    val contextMenuLayout = R.menu.context_menu_artist

    override fun onBindViewHolder(holder: ViewHolder, item: ArtistOrIndex) {
        holder.textView.text = item.name
        val subtitle = artistSubtitle(item, holder.itemView.context)
        holder.subtitle.text = subtitle
        holder.subtitle.isVisible = subtitle != null
        holder.section.text = getSectionForDisplay(item)
        holder.section.isVisible = enableSections
        holder.layout.setOnClickListener { onItemClick(item) }
        holder.layout.setOnLongClickListener {
            val popup = Utils.createPopupMenu(holder.itemView, contextMenuLayout)

            popup.setOnMenuItemClickListener { menuItem ->
                onContextMenuClick(menuItem, item)
            }

            true
        }

        holder.coverArtId = item.coverArt

        val imageLoaderProvider: ImageLoaderProvider by inject()

        if (showArtistPicture()) {
            holder.coverArt.visibility = View.VISIBLE
            CoroutineScope(Dispatchers.IO).launch {
                val key = FileUtil.getArtistArtKey(item.name, false)

                withContext(Dispatchers.Main) {
                    imageLoaderProvider.executeOn {
                        it.loadImage(
                            view = holder.coverArt,
                            id = holder.coverArtId,
                            key = key,
                            large = false,
                            size = 0,
                            defaultResourceId = R.drawable.ic_contact_picture
                        )
                    }
                }
            }
        } else {
            holder.coverArt.visibility = View.GONE
        }
    }

    override fun getSectionName(item: Identifiable): String {
        val index = adapter.items.indexOf(item)
        if (index == -1 || item !is ArtistOrIndex) return ""

        return getSectionFromName(item.name ?: "")
    }

    private fun getSectionForDisplay(item: ArtistOrIndex): String {
        val index = adapter.items.indexOf(item)

        if (index == -1) return " "

        if (index == 0) return getSectionFromName(item.name ?: " ")

        val previousItem = adapter.items[index - 1]
        val previousSectionKey: String

        previousSectionKey = if (previousItem is ArtistOrIndex) {
            getSectionFromName(previousItem.name ?: " ")
        } else {
            " "
        }

        val currentSectionKey = getSectionFromName(item.name ?: "")

        return if (previousSectionKey == currentSectionKey) "" else currentSectionKey
    }

    private fun getSectionFromName(name: String): String {
        if (name.isEmpty()) return SECTION_KEY_DEFAULT
        val section = name.first().uppercaseChar()
        if (!section.isLetter()) return SECTION_KEY_DEFAULT
        return Util.stripAccents(section.toString())
    }

    private fun showArtistPicture(): Boolean = ActiveServerProvider.shouldUseId3Tags() && Settings.shouldShowArtistPicture

    /**
     * Creates an instance of our ViewHolder class
     */
    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        var section: TextView = itemView.findViewById(R.id.row_section)
        var textView: TextView = itemView.findViewById(R.id.row_artist_name)
        var subtitle: TextView = itemView.findViewById(R.id.row_artist_subtitle)
        var layout: RelativeLayout = itemView.findViewById(R.id.containing_layout)
        var coverArt: ImageView = itemView.findViewById(R.id.cover_art)
        var coverArtId: String? = null
    }

    override fun onCreateViewHolder(inflater: LayoutInflater, parent: ViewGroup): ViewHolder = ViewHolder(inflater.inflate(layout, parent, false))

    companion object {
        const val SECTION_KEY_DEFAULT = "#"
    }
}
