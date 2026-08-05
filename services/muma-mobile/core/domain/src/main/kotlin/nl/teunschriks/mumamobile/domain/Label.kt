package nl.teunschriks.mumamobile.domain

import java.io.Serializable

/**
 * A record label, as returned by the server's getLabelList endpoint.
 *
 * Labels are identified by name everywhere they are used as a filter (the PUBLISHER tag), so the
 * numeric [id] only matters for cover art lookups.
 */
data class Label(
    val id: String,
    val name: String,
    val coverArt: String? = null
) : Serializable {
    companion object {
        @Suppress("unused")
        private const val serialVersionUID = 1L
    }
}
