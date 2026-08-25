/*
 * ManagementIndexAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R

/**
 * The management index: group headers and page rows, in the order the web sidebar lists them.
 *
 * A pager with a tab per page stopped working somewhere around six tabs and is hopeless at
 * nineteen, so the section opens on a list of what it contains instead. Pages the app has not built
 * yet are drawn dimmed and do not respond to a tap; [ManagementIndexItem] carries no state of its
 * own, so what is shown is entirely a function of [ManagementPage].
 */
class ManagementIndexAdapter(
    private val onPageSelected: (ManagementPage) -> Unit
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    var items: List<ManagementIndexItem> = emptyList()
        set(value) {
            field = value
            @Suppress("NotifyDataSetChanged")
            notifyDataSetChanged()
        }

    class HeaderViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.management_group_title)
    }

    class PageViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.management_page_title)
        val subtitle: TextView = view.findViewById(R.id.management_page_subtitle)
    }

    override fun getItemCount() = items.size

    override fun getItemViewType(position: Int) = when (items[position]) {
        is ManagementIndexItem.Header -> TYPE_HEADER
        is ManagementIndexItem.Row -> TYPE_PAGE
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)

        return if (viewType == TYPE_HEADER) {
            HeaderViewHolder(
                inflater.inflate(R.layout.management_index_header, parent, false)
            )
        } else {
            PageViewHolder(inflater.inflate(R.layout.management_index_row, parent, false))
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (val item = items[position]) {
            is ManagementIndexItem.Header -> bindHeader(holder as HeaderViewHolder, item)
            is ManagementIndexItem.Row -> bindPage(holder as PageViewHolder, item.page)
        }
    }

    private fun bindHeader(holder: HeaderViewHolder, item: ManagementIndexItem.Header) {
        holder.title.setText(item.group.titleRes ?: R.string.management_label)
    }

    private fun bindPage(holder: PageViewHolder, page: ManagementPage) {
        holder.title.setText(page.titleRes)
        holder.subtitle.visibility = if (page.isBuilt) View.GONE else View.VISIBLE
        holder.subtitle.setText(R.string.management_page_on_the_web)

        holder.itemView.isEnabled = page.isBuilt
        holder.itemView.alpha = if (page.isBuilt) 1f else DISABLED_ALPHA
        holder.itemView.setOnClickListener(
            if (page.isBuilt) View.OnClickListener { onPageSelected(page) } else null
        )
        holder.itemView.isClickable = page.isBuilt
    }

    companion object {
        private const val TYPE_HEADER = 0
        private const val TYPE_PAGE = 1
        private const val DISABLED_ALPHA = 0.45f
    }
}
