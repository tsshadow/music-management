package nl.teunschriks.mumamobile.api.subsonic

import java.net.URI
import java.util.Locale

/**
 * Host matching for "is this server ours": an install made with an older server address (another
 * subdomain of the owner's domain) must still reach the MuMa API. What counts as the owner's
 * domain is a build setting, never guessed from the host, because a suffix such as `duckdns.org`
 * or `co.uk` is shared by unrelated parties.
 */
object ServerHosts {
    private val hostPattern = Regex("^(?:[a-z][a-z0-9+.-]*://)?(?:[^/?#@]*@)?(\\[[^\\]]*]|[^/?#:]*)", RegexOption.IGNORE_CASE)

    /** The lower-case host of [url], or `""`. Scheme, port, path and trailing slash do not count. */
    fun hostOf(url: String): String {
        val trimmed = url.trim()
        if (trimmed.isEmpty()) return ""
        val withScheme = if (trimmed.contains("://")) trimmed else "https://$trimmed"
        val parsed = try {
            URI(withScheme).host
        } catch (_: java.net.URISyntaxException) {
            null
        }
        // URI has no host for a name with an underscore (my_nas.example.org); read it by hand.
        val host = parsed ?: hostPattern.find(trimmed)?.groupValues?.get(1).orEmpty()
        return host.lowercase(Locale.ROOT).trimEnd('.')
    }

    /**
     * Whether the host of [url] belongs to the owner: it equals the host of [ownServerUrl], equals
     * [ownDomain], or is a subdomain of it. An empty [ownDomain] leaves the exact host match only.
     * False if [url] has no host.
     */
    fun isOwn(url: String, ownServerUrl: String, ownDomain: String = ""): Boolean {
        val host = hostOf(url)
        if (host.isEmpty()) return false
        if (host == hostOf(ownServerUrl)) return true
        val domain = ownDomain.trim().lowercase(Locale.ROOT).trim('.')
        return domain.isNotEmpty() && (host == domain || host.endsWith(".$domain"))
    }
}
