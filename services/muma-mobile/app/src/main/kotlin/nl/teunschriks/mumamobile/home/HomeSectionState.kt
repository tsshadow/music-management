/*
 * HomeSectionState.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.home

/**
 * What one home screen slot should be showing right now.
 *
 * The home screen used to render nothing at all until every section had finished loading, which on
 * a cold start meant several seconds of empty black. Sections therefore report their own state and
 * the screen draws a placeholder for the ones still on their way.
 */
sealed interface HomeSectionState {

    /** Still loading: the slot shows its skeleton. */
    data object Loading : HomeSectionState

    /** Loaded, but the section has nothing worth showing: the slot is hidden. */
    data object Empty : HomeSectionState

    /**
     * Showing what was on screen the last time the app ran, while a fresh copy is on its way.
     *
     * Distinct from [Content] rather than a flag on it because the two differ in what the screen
     * should do next: a stale slot spins its progress bar, a content slot does not. It matters most
     * when the refresh fails -- the cards stay, but the bar has to stop, or it promises something
     * that is not coming.
     */
    data class Stale(val section: HomeSection) : HomeSectionState

    /** Loaded with content. */
    data class Content(val section: HomeSection) : HomeSectionState
}
