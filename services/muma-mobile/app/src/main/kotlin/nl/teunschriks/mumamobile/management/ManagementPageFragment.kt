/*
 * ManagementPageFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import androidx.fragment.app.Fragment
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.fragment.FragmentTitle
import nl.teunschriks.mumamobile.util.Util.toast
import org.koin.androidx.viewmodel.ext.android.activityViewModel

/**
 * One Beheer page: downloaders, users, or access requests.
 *
 * The three differ only in what they list and which actions each row offers, so like the Library
 * browse pages they share a fragment parameterized by an enum. Reached from
 * [ManagementFragment]'s index, which only offers a row for a page [ManagementPage.isBuilt] says
 * exists; a page this fragment does not know shows an empty list rather than crashing.
 */
class ManagementPageFragment : Fragment() {

    private val viewModel: ManagementViewModel by activityViewModel()
    private val adapter = ManagementRowAdapter()

    private val page: ManagementPage
        get() = ManagementPage.valueOf(
            arguments?.getString(ARG_PAGE) ?: ManagementPage.DOWNLOADERS.name
        )

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_management_list, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, page.titleRes)

        val recycler: RecyclerView = view.findViewById(R.id.management_recycler)
        recycler.layoutManager = LinearLayoutManager(requireContext())
        recycler.adapter = adapter

        if (page == ManagementPage.USER_REQUESTS) setupStatusFilter(view)
        if (page == ManagementPage.EVENTS) setupLevelFilter(view)

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                observe()
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.error.collectLatest { message ->
                    if (message != null) {
                        toast(getString(R.string.management_action_failed, message))
                        viewModel.clearError()
                    }
                }
            }
        }

        load()
    }

    private fun load() = when (page) {
        ManagementPage.DOWNLOADERS -> viewModel.loadDownloadAccounts()
        ManagementPage.USERS -> viewModel.loadUsers()
        ManagementPage.USER_REQUESTS -> viewModel.loadRequests()
        ManagementPage.OVERVIEW -> viewModel.loadOverview()
        ManagementPage.HEALTH -> viewModel.loadContainers()
        ManagementPage.EVENTS -> viewModel.loadEvents()
        ManagementPage.TAGGER -> viewModel.loadTagger()
        ManagementPage.GENRE_CURATION -> viewModel.loadGenreQueue()
        ManagementPage.PODCAST_CURATION -> viewModel.loadPodcastQueue()
        ManagementPage.LABEL_PROPOSALS -> viewModel.loadLabelProposals()
        else -> Unit
    }

    private suspend fun observe() = when (page) {
        ManagementPage.DOWNLOADERS ->
            combine(viewModel.soundcloud, viewModel.youtube) { soundcloud, youtube ->
                soundcloud.map { it.toRow(DownloadSource.SOUNDCLOUD) } +
                    youtube.map { it.toRow(DownloadSource.YOUTUBE) }
            }.collectLatest { adapter.items = it }

        ManagementPage.USERS ->
            viewModel.users.collectLatest { users -> adapter.items = users.map { it.toRow() } }

        ManagementPage.USER_REQUESTS ->
            viewModel.requests.collectLatest { requests ->
                adapter.items = requests.map { it.toRow() }
            }

        ManagementPage.OVERVIEW ->
            viewModel.overview.filterNotNull().collectLatest { adapter.items = it.toRows() }

        ManagementPage.HEALTH ->
            viewModel.containers.collectLatest { containers ->
                adapter.items = containers.map { it.toRow() }
            }

        ManagementPage.EVENTS ->
            viewModel.events.collectLatest { events ->
                adapter.items = events.map { it.toRow() }.ifEmpty {
                    // A log with nothing in it and a filter that matched nothing look identical
                    // otherwise: an empty list under a level chip reads as a page that failed.
                    listOf(ManagementRow(id = "empty", title = getString(R.string.management_events_empty), subtitle = null))
                }
            }

        ManagementPage.TAGGER ->
            viewModel.tagger.filterNotNull().collectLatest { adapter.items = it.toRows() }

        ManagementPage.GENRE_CURATION ->
            viewModel.genres.collectLatest { genres ->
                adapter.items = genres.map { it.toRow() }.orEmptyQueue()
            }

        ManagementPage.PODCAST_CURATION ->
            viewModel.podcasts.collectLatest { podcasts ->
                adapter.items = podcasts.map { it.toRow() }.orEmptyQueue()
            }

        ManagementPage.LABEL_PROPOSALS ->
            viewModel.proposals.collectLatest { proposals ->
                adapter.items = proposals.map { it.toRow() }.orEmptyQueue()
            }

        else -> Unit
    }

    /** A count and its noun agree, which a formatted string cannot do across languages. */
    private fun quantity(plural: Int, count: Int): String = resources.getQuantityString(plural, count, count)

    /**
     * An empty curation queue is the good outcome, and an empty list does not say so -- it reads
     * the same as a page that failed to load. The same reasoning as the events page.
     */
    private fun List<ManagementRow>.orEmptyQueue(): List<ManagementRow> = ifEmpty {
        listOf(
            ManagementRow(
                id = "empty",
                title = getString(R.string.management_queue_empty),
                subtitle = null
            )
        )
    }

    /**
     * Whether the tagger is busy, then one line per reason files are queued.
     *
     * The action sits on the status row rather than on each reason: a retag is not per-reason, it
     * walks everything that is marked.
     */
    private fun ManagementViewModel.TaggerStatus.toRows(): List<ManagementRow> {
        val status = ManagementRow(
            id = "status",
            title = getString(
                if (health.busy) R.string.management_tagger_busy else R.string.management_tagger_idle
            ),
            subtitle = quantity(R.plurals.management_tagger_pending_total, pending.total),
            primary = RowAction(getString(R.string.management_tagger_run)) { viewModel.startRetag() }
        )
        return listOf(status) + pending.byReason.map { reason ->
            ManagementRow(
                id = "reason:${reason.reason}",
                title = reason.reason,
                subtitle = quantity(R.plurals.management_tagger_pending_reason, reason.count)
            )
        }
    }

    private fun nl.teunschriks.mumamobile.api.muma.MumaGenreRule.toRow(): ManagementRow {
        // A genre that already rewrites onto others says so: deciding it black without seeing that
        // would look like discarding the tracks rather than moving them.
        val targets = canonicalTargets.joinToString(", ") { it.name }
        return ManagementRow(
            id = id.toString(),
            title = name,
            subtitle = listOfNotNull(
                quantity(R.plurals.management_curation_occurrences, occurrences),
                targets.takeIf { it.isNotBlank() }
            ).joinToString(" \u00b7 "),
            primary = RowAction(getString(R.string.management_curation_keep)) {
                viewModel.decideGenre(id, ManagementRepository.CURATION_WHITE)
            },
            secondary = RowAction(getString(R.string.management_curation_drop)) {
                viewModel.decideGenre(id, ManagementRepository.CURATION_BLACK)
            }
        )
    }

    private fun nl.teunschriks.mumamobile.api.muma.MumaPodcastRule.toRow() = ManagementRow(
        id = id.toString(),
        title = name,
        subtitle = listOfNotNull(
            quantity(R.plurals.management_curation_occurrences, occurrences),
            station,
            host,
            aliases.takeIf { it.isNotEmpty() }
                ?.let { quantity(R.plurals.management_curation_aliases, it.size) }
        ).joinToString(" \u00b7 "),
        primary = RowAction(getString(R.string.management_curation_keep)) {
            viewModel.decidePodcast(id, ManagementRepository.CURATION_WHITE)
        },
        secondary = RowAction(getString(R.string.management_curation_drop)) {
            viewModel.decidePodcast(id, ManagementRepository.CURATION_BLACK)
        }
    )

    private fun nl.teunschriks.mumamobile.api.muma.MumaLabelProposal.toRow() = ManagementRow(
        id = id.toString(),
        // The folder is a full path and the last element is the release, which is the part that
        // identifies it; the rest is the same import directory on every row.
        title = folder.substringAfterLast('/').ifBlank { folder },
        subtitle = listOfNotNull(
            proposedLabel ?: getString(R.string.management_proposal_no_label),
            catid,
            source
        ).joinToString(" \u00b7 "),
        primary = RowAction(getString(R.string.management_proposal_confirm)) {
            askForLabel(this)
        },
        secondary = RowAction(getString(R.string.management_proposal_reject)) {
            viewModel.rejectProposal(id)
        }
    )

    /**
     * Confirming asks for the label even when the proposal already carries one.
     *
     * The server takes the label from the body rather than from the row, and the proposals worth
     * looking at on a phone are exactly the ones where it guessed nothing -- so a one-tap confirm
     * would either send an empty label or quietly file a release under a guess.
     */
    private fun askForLabel(proposal: nl.teunschriks.mumamobile.api.muma.MumaLabelProposal) {
        val input = EditText(requireContext()).apply {
            setText(proposal.proposedLabel.orEmpty())
            setSelection(text.length)
        }
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.management_proposal_confirm))
            .setMessage(proposal.folder)
            .setView(input)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val label = input.text.toString().trim()
                if (label.isEmpty()) {
                    toast(getString(R.string.management_proposal_label_required))
                } else {
                    viewModel.confirmProposal(proposal.id, label)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun setupLevelFilter(view: View) {
        val header: LinearLayout = view.findViewById(R.id.management_header)
        header.visibility = View.VISIBLE

        addFilterButton(header, getString(R.string.management_events_all)) { viewModel.loadEvents(null) }
        EVENT_LEVELS.forEach { level ->
            // The label is the server's own word for the level; translating it would hide which
            // value the filter actually sends, and the level is what the log itself prints.
            addFilterButton(header, level) { viewModel.loadEvents(level) }
        }
    }

    private fun addFilterButton(header: LinearLayout, label: String, onClick: () -> Unit) {
        val button = Button(requireContext())
        button.text = label
        button.setOnClickListener { onClick() }
        header.addView(button)
    }

    /**
     * Three lines rather than the web's cards: how much of the stack is up, which version answers,
     * and when the library last grew. The rest of the web overview is a chart, which is not what a
     * phone is for.
     */
    private fun SystemOverview.toRows(): List<ManagementRow> = listOf(
        ManagementRow(
            id = "containers",
            title = getString(R.string.management_system_containers, running, total),
            subtitle = if (allRunning) {
                getString(R.string.management_system_all_running)
            } else {
                getString(R.string.management_system_offline, offline.joinToString(", "))
            }
        ),
        ManagementRow(
            id = "version",
            title = version ?: getString(R.string.management_system_version_unknown),
            subtitle = getString(R.string.management_system_version)
        ),
        ManagementRow(
            id = "activity",
            title = lastAdded?.let { listOfNotNull(it.artist, it.title).joinToString(" - ") }
                ?: getString(R.string.management_system_no_activity),
            subtitle = lastAdded?.timestamp?.let {
                "${getString(R.string.management_system_last_added)} \u00b7 $it"
            } ?: getString(R.string.management_system_last_added)
        )
    )

    private fun nl.teunschriks.mumamobile.api.muma.MumaContainer.toRow() = ManagementRow(
        id = name,
        title = name,
        subtitle = listOfNotNull(status, image).joinToString(" \u00b7 "),
        primary = RowAction(getString(R.string.management_logs)) { showLogs(name) }
    )

    private fun nl.teunschriks.mumamobile.api.muma.MumaEvent.toRow() = ManagementRow(
        id = id.toString(),
        title = title ?: message.orEmpty().lineSequence().firstOrNull().orEmpty(),
        subtitle = listOfNotNull(level, source, createdAt).joinToString(" \u00b7 ")
    )

    /**
     * The log tail in a dialog rather than a page of its own: it is a wall of text with nothing to
     * do in it, and giving it a destination would put a screen in the back stack that the reader
     * only ever wants to dismiss.
     */
    private fun showLogs(name: String) {
        val dialog = AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.management_logs_title, name))
            .setMessage(getString(R.string.management_logs_loading))
            .setPositiveButton(android.R.string.ok, null)
            .show()

        viewLifecycleOwner.lifecycleScope.launch {
            val logs = runCatching { viewModel.containerLogs(name) }
                .getOrElse { getString(R.string.management_action_failed, it.message ?: name) }
            if (dialog.isShowing) {
                dialog.setMessage(logs.ifBlank { getString(R.string.management_logs_empty) })
            }
        }
    }

    private fun setupStatusFilter(view: View) {
        val header: LinearLayout = view.findViewById(R.id.management_header)
        header.visibility = View.VISIBLE

        listOf(
            ManagementViewModel.STATUS_PENDING to R.string.management_status_pending,
            ManagementViewModel.STATUS_APPROVED to R.string.management_status_approved,
            ManagementViewModel.STATUS_REJECTED to R.string.management_status_rejected
        ).forEach { (status, labelRes) ->
            val button = Button(requireContext())
            button.text = getString(labelRes)
            button.setOnClickListener { viewModel.loadRequests(status) }
            header.addView(button)
        }
    }

    private fun nl.teunschriks.mumamobile.api.muma.MumaDownloadAccount.toRow(
        source: DownloadSource
    ) = ManagementRow(
        id = "$source:$name",
        title = name,
        subtitle = getString(
            if (source == DownloadSource.SOUNDCLOUD) {
                R.string.management_source_soundcloud
            } else {
                R.string.management_source_youtube
            }
        ),
        primary = RowAction(getString(R.string.common_delete)) {
            viewModel.deleteDownloadAccount(source, name)
        }
    )

    private fun nl.teunschriks.mumamobile.api.muma.MumaAuthUser.toRow(): ManagementRow {
        val isEnabled = enabled != false

        return ManagementRow(
            id = id.toString(),
            title = display_name ?: username,
            subtitle = listOfNotNull(
                email,
                role_name,
                getString(
                    if (isEnabled) R.string.management_enabled else R.string.management_disabled
                )
            ).joinToString(" · "),
            primary = RowAction(
                getString(if (isEnabled) R.string.management_disable else R.string.management_enable)
            ) {
                viewModel.setUserEnabled(id, !isEnabled)
            }
        )
    }

    private fun nl.teunschriks.mumamobile.api.muma.MumaAccessRequest.toRow(): ManagementRow {
        val pending = status == ManagementViewModel.STATUS_PENDING

        return ManagementRow(
            id = id.toString(),
            title = display_name,
            subtitle = listOfNotNull(email, requested_at).joinToString(" · "),
            primary = if (pending) {
                RowAction(getString(R.string.management_approve)) { viewModel.approve(id) }
            } else {
                RowAction(getString(R.string.management_unapprove)) { viewModel.unapprove(id) }
            },
            secondary = if (pending) {
                RowAction(getString(R.string.management_reject)) { viewModel.reject(id) }
            } else {
                null
            }
        )
    }

    companion object {
        private const val ARG_PAGE = "managementPage"

        fun argumentsFor(page: ManagementPage): Bundle = Bundle().apply { putString(ARG_PAGE, page.name) }
    }
}
