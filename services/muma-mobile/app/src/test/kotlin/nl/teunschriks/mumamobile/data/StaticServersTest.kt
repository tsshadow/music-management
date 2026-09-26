/*
 * StaticServersTest.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.data

import org.amshove.kluent.shouldBeEqualTo
import org.amshove.kluent.shouldBeFalse
import org.amshove.kluent.shouldBeTrue
import org.amshove.kluent.shouldStartWith
import org.junit.Test

/**
 * The one server the app signs in to shipped with `allowSelfSignedCertificate = true`, which
 * installs a trust-all certificate manager and hostname verifier for a server that has a valid
 * certificate (bug report 054). These pin the transport settings of that server.
 */
class StaticServersTest {

    private val server = StaticServers.STATIC_SERVERS.single()

    @Test
    fun `the server is reached over https with certificate checks on`() {
        server.url shouldStartWith "https://"
        server.allowSelfSignedCertificate.shouldBeFalse()
        StaticServers.ALLOW_SELF_SIGNED_CERTIFICATE.shouldBeFalse()
    }

    /**
     * LMS verifies a `t`/`s` token against the per-user Subsonic API token, not the login password
     * the app holds, so the salted form would lock every account out. Flip this together with the
     * work in GitLab issue #21, not on its own.
     */
    @Test
    fun `the password mode is the hex form LMS accepts for a login password`() {
        server.forcePlainTextPassword.shouldBeTrue()
        server.forcePlainTextPassword shouldBeEqualTo StaticServers.FORCE_PLAIN_TEXT_PASSWORD
    }
}
