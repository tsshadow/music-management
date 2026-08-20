/*
 * VoiceDiagnosticsFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Util.applyTheme
import nl.teunschriks.mumamobile.voice.MusicServiceVocabulary
import nl.teunschriks.mumamobile.voice.ParsedQuery
import nl.teunschriks.mumamobile.voice.QueryResolver
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceQuery
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import timber.log.Timber

/**
 * Shows what every voice request did, and lets one be typed.
 *
 * Assistant rewrites an utterance before MuMa is called, and none of that rewriting is visible from
 * a track count. Each row here is one request: what arrived, every extra that came with it, the
 * tokens, the rules that fired, what the library said about each term and what was finally asked
 * for. Tapping a row opens the whole story; long-pressing shares it.
 *
 * The text field is the third entry point into the same pipeline. It parses and resolves exactly
 * what the microphone and the car do, so a phrasing can be tried out at a desk rather than on a
 * motorway.
 */
class VoiceDiagnosticsFragment : Fragment() {

    private var list: RecyclerView? = null
    private var empty: TextView? = null
    private val adapter = TraceAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme(this.context)
        super.onCreate(savedInstanceState)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.voice_diagnostics, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, getString(R.string.voice_diagnostics_title))

        list = view.findViewById<RecyclerView>(R.id.voice_diagnostics_list)?.apply {
            layoutManager = LinearLayoutManager(requireContext())
            adapter = this@VoiceDiagnosticsFragment.adapter
        }
        empty = view.findViewById(R.id.voice_diagnostics_empty)

        val input = view.findViewById<EditText>(R.id.voice_diagnostics_input)
        input?.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                val typed = input.text.toString().trim()
                if (typed.isNotEmpty()) {
                    input.text.clear()
                    runTyped(typed)
                }
                true
            } else {
                false
            }
        }

        view.findViewById<Button>(R.id.voice_diagnostics_clear)?.setOnClickListener {
            VoiceTraceLog.clear()
            refresh()
        }

        refresh()
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    /**
     * Runs a typed query through the same parser and resolver the car uses.
     *
     * Off the main thread, because resolving asks the library for its genres and labels. Nothing is
     * played: the point is the trace, not the music.
     */
    private fun runTyped(query: String) {
        val trace = QueryTrace(VoiceEntryPoint.TEXT_INPUT, "app")
        lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                runCatching {
                    val vocabulary =
                        MusicServiceVocabulary(MusicServiceFactory.getMusicService())
                    val parsed = VoiceQuery.parse(query, trace)
                    QueryResolver(vocabulary).resolve(parsed ?: ParsedQuery(), null, trace)
                }.onFailure {
                    Timber.w(it, "typed voice query failed")
                    trace.outcome("failed: ${it.javaClass.simpleName}")
                }
                VoiceTraceLog.record(trace)
            }
            refresh()
        }
    }

    private fun refresh() {
        val traces = VoiceTraceLog.recent()
        adapter.submit(traces)
        empty?.visibility = if (traces.isEmpty()) View.VISIBLE else View.GONE
        list?.visibility = if (traces.isEmpty()) View.GONE else View.VISIBLE
    }

    private inner class TraceAdapter : RecyclerView.Adapter<TraceAdapter.Row>() {

        private var traces: List<QueryTrace> = emptyList()
        private val expanded = mutableSetOf<Int>()

        fun submit(next: List<QueryTrace>) {
            traces = next
            expanded.clear()
            @Suppress("NotifyDataSetChanged")
            notifyDataSetChanged()
        }

        override fun getItemCount(): Int = traces.size

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Row = Row(
            LayoutInflater.from(parent.context)
                .inflate(R.layout.voice_diagnostics_row, parent, false)
        )

        override fun onBindViewHolder(holder: Row, position: Int) {
            val trace = traces[position]
            holder.summary.text = trace.summary
            holder.detail.text = trace.render()

            val isOpen = position in expanded
            holder.detailScroll.visibility = if (isOpen) View.VISIBLE else View.GONE

            holder.itemView.setOnClickListener {
                // The bound position, not the captured one: a row that has been rebound since is
                // holding a stale index, and toggling that opens somebody else's trace.
                val at = holder.bindingAdapterPosition
                if (at == RecyclerView.NO_POSITION) return@setOnClickListener
                if (at in expanded) expanded.remove(at) else expanded.add(at)
                notifyItemChanged(at)
            }
            holder.itemView.setOnLongClickListener {
                share(trace)
                true
            }
        }

        private inner class Row(view: View) : RecyclerView.ViewHolder(view) {
            val summary: TextView = view.findViewById(R.id.voice_trace_summary)
            val detail: TextView = view.findViewById(R.id.voice_trace_detail)
            val detailScroll: View = view.findViewById(R.id.voice_trace_detail_scroll)
        }
    }

    /** The sharing the log files never got, which is why the buffer is the sink that matters. */
    private fun share(trace: QueryTrace) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, getString(R.string.voice_diagnostics_title))
            putExtra(Intent.EXTRA_TEXT, trace.render())
        }
        startActivity(Intent.createChooser(intent, getString(R.string.voice_diagnostics_share)))
    }
}
