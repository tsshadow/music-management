package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.muma.MumaTokenStorage

/**
 * Provides configuration for [SubsonicAPIClient].
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
    val tokenStorage: MumaTokenStorage? = null
)
