package nl.teunschriks.mumamobile.api.subsonic

import java.net.URI
import java.util.Locale

/**
 * Host matching for "is this server one of ours": an install made with an older server address
 * (another subdomain of the same domain, or the pre-rebrand name) must still reach the MuMa API.
 */
object ServerHosts {
    /** The lower-case host of [url], or `""`. Scheme, port, path and trailing slash do not count. */
    fun hostOf(url: String): String {
        val trimmed = url.trim()
        if (trimmed.isEmpty()) return ""
        val withScheme = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        return try {
            URI(withScheme).host?.lowercase(Locale.ROOT)?.trimEnd('.').orEmpty()
        } catch (_: java.net.URISyntaxException) {
            ""
        }
    }

    /**
     * The registrable parent of [host]: its last two labels. `localhost`, a single label and an IP
     * address stand for themselves, so two different IPs are never "the same party".
     */
    private fun partyOf(host: String): String {
        val labels = host.split('.')
        val isIp = host.contains(':') || labels.all { it.isNotEmpty() && it.all(Char::isDigit) }
        return if (isIp || labels.size < 3) host else labels.takeLast(2).joinToString(".")
    }

    /** Whether the hosts of [a] and [b] are equal or share a parent domain. False if either is empty. */
    fun sameParty(a: String, b: String): Boolean {
        val hostA = hostOf(a)
        val hostB = hostOf(b)
        return hostA.isNotEmpty() && hostB.isNotEmpty() && partyOf(hostA) == partyOf(hostB)
    }
}
