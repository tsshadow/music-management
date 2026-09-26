package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.muma.MumaTokenStorage
import nl.teunschriks.mumamobile.api.subsonic.interceptors.SubsonicTokenRecovery

/**
 * Provides configuration for [SubsonicAPIClient].
 *
 * [tokenRecovery], when set, lets the client replace a Subsonic token LMS refused and retry the
 * request once (issue #73); `null` for the offline database and in tests.
 */
data class SubsonicClientConfiguration(
    val baseUrl: String,
    val username: String,
    val password: String,
    val apiKey: String? = null,
    val minimalProtocolVersion: SubsonicAPIVersions,
    val clientID: String,
    val allowSelfSignedCertificate: Boolean = false,
    val forcePlainTextPassword: Boolean = false,
    val debug: Boolean = false,
    val isRealProtocolVersion: Boolean = false,
    val mumaUserId: Int? = null,
    val tokenStorage: MumaTokenStorage? = null,
    val tokenRecovery: SubsonicTokenRecovery? = null
)
