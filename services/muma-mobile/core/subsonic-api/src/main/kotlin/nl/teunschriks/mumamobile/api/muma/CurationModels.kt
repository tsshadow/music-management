/*
 * CurationModels.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.api.muma

import com.google.gson.annotations.SerializedName

/**
 * The four curation queues behind the Beheer tagger pages.
 *
 * Every one of these is a row a person has to decide on, which is why they are modelled and the
 * rest of each endpoint's answer is not: the app shows the queue and sends the decision back.
 */

/** One row of `/api/rules/genres`. `occurrences` is how many files carry the genre. */
data class MumaGenreRule(
    val id: Int = 0,
    val name: String = "",
    val state: String? = null,
    val occurrences: Int = 0,
    @SerializedName("detected_at") val detectedAt: String? = null,
    @SerializedName("decided_at") val decidedAt: String? = null,
    @SerializedName("decided_by") val decidedBy: String? = null,
    @SerializedName("canonical_targets") val canonicalTargets: List<MumaGenreTarget> = emptyList()
)

/** A genre a decision rewrites onto; several of them is a contraction, not a mistake. */
data class MumaGenreTarget(
    val id: Int = 0,
    val name: String = ""
)

/**
 * A decision on a genre, always carrying the rewrite targets the row already has.
 *
 * The server replaces rather than merges: it deletes every row in `rules_genre_expansions` for
 * this genre and inserts what the request carries, so leaving the field out is not "unchanged", it
 * is "no rewrite". A phone that only decides the state would therefore silently destroy the
 * correction the row displays. Choosing *new* targets needs a picker over the whole genre table
 * and stays on the web.
 */
data class MumaGenreDecisionRequest(
    val state: String,
    @SerializedName("canonical_ids") val canonicalIds: List<Int> = emptyList()
)

/** One row of `/api/rules/podcasts`: a radio show or podcast series awaiting a decision. */
data class MumaPodcastRule(
    val id: Int = 0,
    val name: String = "",
    val state: String? = null,
    val occurrences: Int = 0,
    val host: String? = null,
    val station: String? = null,
    val aliases: List<String> = emptyList()
)

/** A decision on a show. Merging into another show is web-only, for the same reason as above. */
data class MumaPodcastDecisionRequest(
    val state: String
)

/** One row of `/api/label-proposals`: a release the importer could not place. */
data class MumaLabelProposal(
    val id: Int = 0,
    val folder: String = "",
    val catid: String? = null,
    @SerializedName("proposed_label") val proposedLabel: String? = null,
    val source: String? = null,
    val confidence: Double? = null,
    val status: String? = null
)

/** Confirming a proposal takes the label to file it under; the server needs it even to agree. */
data class MumaLabelDecisionRequest(
    val label: String
)

/**
 * What confirming actually did.
 *
 * Not every 200 is a confirmation: the folder may have been moved away since the proposal was
 * written (`stale`), or the destination may already hold a release, in which case the release stays
 * in import and the proposal stays open. Both answer 200, so only this body distinguishes them.
 */
data class MumaLabelConfirmResponse(
    val status: String? = null,
    val folder: String? = null,
    val destination: String? = null
)

/** `/api/tagger/retag/pending`: how many files a rule change queued up, and which change did it. */
data class MumaRetagPending(
    val total: Int = 0,
    @SerializedName("by_reason") val byReason: List<MumaRetagReason> = emptyList()
)

data class MumaRetagReason(
    val reason: String = "",
    val count: Int = 0
)

/** `/api/tagger/health`: whether a tagging run currently holds the lock. */
data class MumaTaggerHealth(
    val status: String? = null,
    val busy: Boolean = false
)
