/*
 * ManualAdapter.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.manual

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.text.HtmlCompat
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R

/**
 * Renders [manualChapters] as a list of collapsed headings that open one at a time.
 *
 * Collapsed by default on purpose: twelve chapters expanded is a document nobody scrolls to the
 * end of, and the headings alone already answer "does this app do X".
 */
class ManualAdapter(
    private val chapters: List<ManualChapter>,
    private val onAction: (chapter: ManualChapter) -> Unit,
    private val onScreenshot: (chapter: ManualChapter) -> Unit
) : RecyclerView.Adapter<ManualAdapter.ChapterHolder>() {

    private val expanded = mutableSetOf<Int>()

    class ChapterHolder(view: View) : RecyclerView.ViewHolder(view) {
        val header: View = view.findViewById(R.id.manual_chapter_header)
        val icon: ImageView = view.findViewById(R.id.manual_chapter_icon)
        val title: TextView = view.findViewById(R.id.manual_chapter_title)
        val chevron: ImageView = view.findViewById(R.id.manual_chapter_chevron)
        val content: View = view.findViewById(R.id.manual_chapter_content)
        val body: TextView = view.findViewById(R.id.manual_chapter_body)
        val screenshot: ImageView = view.findViewById(R.id.manual_chapter_image)
        val action: TextView = view.findViewById(R.id.manual_chapter_action)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChapterHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.manual_chapter_row, parent, false)
        return ChapterHolder(view)
    }

    override fun getItemCount(): Int = chapters.size

    override fun onBindViewHolder(holder: ChapterHolder, position: Int) {
        val chapter = chapters[position]
        val isOpen = expanded.contains(position)
        val context = holder.itemView.context

        holder.icon.setImageResource(chapter.icon)
        holder.title.text = context.getString(chapter.title)
        holder.chevron.rotation = if (isOpen) 90f else 0f
        holder.content.visibility = if (isOpen) View.VISIBLE else View.GONE

        holder.body.text = HtmlCompat.fromHtml(
            context.getString(chapter.body),
            HtmlCompat.FROM_HTML_MODE_COMPACT
        )

        if (chapter.screenshot != null) {
            holder.screenshot.visibility = View.VISIBLE
            holder.screenshot.setImageResource(chapter.screenshot)
            holder.screenshot.setOnClickListener { onScreenshot(chapter) }
        } else {
            holder.screenshot.visibility = View.GONE
            holder.screenshot.setOnClickListener(null)
        }

        if (chapter.actionLabel != null && chapter.actionDestination != null) {
            holder.action.visibility = View.VISIBLE
            holder.action.text = context.getString(chapter.actionLabel)
            holder.action.setOnClickListener { onAction(chapter) }
        } else {
            holder.action.visibility = View.GONE
            holder.action.setOnClickListener(null)
        }

        holder.header.setOnClickListener {
            // The position captured at bind time goes stale as soon as anything is inserted; ask
            // the holder where it is now.
            val current = holder.bindingAdapterPosition
            if (current == RecyclerView.NO_POSITION) return@setOnClickListener
            if (!expanded.remove(current)) expanded.add(current)
            notifyItemChanged(current)
        }
    }
}
