/*
 * MemoriesViewModel.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import java.time.LocalDate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.domain.MemoryGroup
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import timber.log.Timber

/**
 * The full Memories screen: one section per release year, newest first.
 *
 * Unlike the home carousel this keeps every track of every group -- the carousel is a teaser, this
 * is the whole day.
 */
class MemoriesViewModel : ViewModel() {

    private val mutableSections = MutableStateFlow<List<HomeSection>>(emptyList())
    val sections: StateFlow<List<HomeSection>> = mutableSections.asStateFlow()

    private val mutableLoaded = MutableStateFlow(false)

    /** False until the first load finishes, so the screen can tell "empty" from "not yet". */
    val loaded: StateFlow<Boolean> = mutableLoaded.asStateFlow()

    // Kept so that tapping a track can play it without a second request.
    private var tracksById: Map<String, Track> = emptyMap()

    fun trackFor(id: String): Track? = tracksById[id]

    fun load() {
        viewModelScope.launch {
            val groups = withContext(Dispatchers.IO) {
                // A server without the endpoint is not a failure worth showing; it simply has no
                // memories, which the empty state already says.
                runCatching { getMusicService().getMemories(LocalDate.now().toString()) }
                    .onFailure { Timber.w(it, "Memories are not available on this server") }
                    .getOrDefault(emptyList())
            }

            tracksById = groups.flatMap { it.tracks }.associateBy { it.id }
            mutableSections.value = sectionsFor(groups)
            mutableLoaded.value = true
        }
    }

    companion object {
        /**
         * One section per group.
         *
         * A heading only says "today" for a group that really contains today's date; one that
         * exists because of the surrounding-days window says "this week" instead, so the screen
         * never claims a precision the tags do not have.
         */
        fun sectionsFor(groups: List<MemoryGroup>): List<HomeSection> = groups.map { group ->
            HomeSection(
                titleRes = memoryHeadingRes(group),
                style = CardStyle.CAROUSEL,
                cards = group.tracks.map { it.toHomeCard() },
                titleArgs = memoryHeadingArgs(group)
            )
        }
    }
}
