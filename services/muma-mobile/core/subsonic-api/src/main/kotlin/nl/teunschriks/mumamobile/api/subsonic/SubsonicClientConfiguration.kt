package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.muma.MumaTokenStorage
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery

/**
 * Provides configuration for [SubsonicAPIClient].
 *
 * Every request is signed with a Subsonic token, never with the password (issue #72). [token] is
 * the token stored when the client was built. When it is `null`, [tokenRecovery] is asked for one
 * per request ([SubsonicTokenRecovery.obtain], which fetches it from MuMa); with neither, requests
 * fail with [nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenUnavailableException]
 * and are never sent. [tokenRecovery], when set, also lets the client replace a token LMS refused
 * and retry the request once (issue #73); `null` for the offline database and in tests.
 */
data class SubsonicClientConfiguration(
    val baseUrl: String,
    val username: String,
    val token: String?,
    val apiKey: String? = null,
    val minimalProtocolVersion: SubsonicAPIVersions,
    val clientID: String,
    val debug: Boolean = false,
    val isRealProtocolVersion: Boolean = false,
    val mumaUserId: Int? = null,
    val tokenStorage: MumaTokenStorage? = null,
    val tokenRecovery: SubsonicTokenRecovery? = null,
    /** The build's own server; a server on its [ownDomain] gets [mumaApiUrl] as its MuMa API. */
    val ownServerUrl: String = "",
    /** Own host of the MuMa API, or empty for `<server>/muma`. */
    val mumaApiUrl: String = "",
    /** The owner's domain: [ownServerUrl] and its subdomains count as the build's own server. */
    val ownDomain: String = ""
)
