package nl.teunschriks.mumamobile.util

import nl.teunschriks.mumamobile.domain.Track

/**
 * Created by Josh on 12/17/13.
 */
data class ShareDetails(val entries: List<Track>) {
    var description: String? = null
    var shareOnServer = false
    var expiration: Long = 0
}
