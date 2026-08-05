/*
 * ManagementRowAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R

/**
 * One row with a title, a subtitle and up to two actions.
 *
 * All three Beheer pages are lists of exactly that shape, so they share this adapter rather than
 * getting one each — the same reasoning behind [nl.teunschriks.mumamobile.home.HomeCardAdapter].
 */
data class ManagementRow(
    val id: String,
    val title: String,
    val subtitle: String?,
    val primary: RowAction? = null,
    val secondary: RowAction? = null
)

data class RowAction(val label: String, val onClick: () -> Unit)

class ManagementRowAdapter : RecyclerView.Adapter<ManagementRowAdapter.ViewHolder>() {

    var items: List<ManagementRow> = emptyList()
        set(value) {
            field = value
            @Suppress("NotifyDataSetChanged")
            notifyDataSetChanged()
        }

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val title: TextView = view.findViewById(R.id.row_title)
        val subtitle: TextView = view.findViewById(R.id.row_subtitle)
        val primary: Button = view.findViewById(R.id.row_primary_action)
        val secondary: Button = view.findViewById(R.id.row_secondary_action)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) = ViewHolder(
        LayoutInflater.from(parent.context).inflate(R.layout.management_row, parent, false)
    )

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val row = items[position]

        holder.title.text = row.title
        holder.subtitle.text = row.subtitle.orEmpty()
        holder.subtitle.visibility = if (row.subtitle.isNullOrBlank()) View.GONE else View.VISIBLE

        bind(holder.primary, row.primary)
        bind(holder.secondary, row.secondary)
    }

    override fun getItemCount() = items.size

    private fun bind(button: Button, action: RowAction?) {
        if (action == null) {
            button.visibility = View.GONE
            button.setOnClickListener(null)
        } else {
            button.visibility = View.VISIBLE
            button.text = action.label
            button.setOnClickListener { action.onClick() }
        }
    }
}
