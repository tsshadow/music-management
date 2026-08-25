/*
 * ManagementPageFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.management

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import androidx.fragment.app.Fragment
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.koin.androidx.viewmodel.ext.android.activityViewModel
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.fragment.FragmentTitle
import nl.teunschriks.mumamobile.util.Util.toast

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

        else -> Unit
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

        fun argumentsFor(page: ManagementPage): Bundle =
            Bundle().apply { putString(ARG_PAGE, page.name) }
    }
}

