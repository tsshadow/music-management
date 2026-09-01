package nl.teunschriks.mumamobile.management

import nl.teunschriks.mumamobile.api.muma.MumaAuthUser
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Admin detection decides whether the Beheer tab is shown at all, so it is worth pinning down.
 * It mirrors `rbac.is_admin_auth` in music-manager.
 */
class ManagementRepositoryTest {

    private fun user(role: String?, isAdmin: Boolean? = null) = MumaAuthUser(
        id = 1,
        username = "someone",
        role_name = role,
        is_admin = isAdmin
    )

    @Test
    fun `a system key is admin`() {
        ManagementRepository.isAdmin("system", null) `should be equal to` true
    }

    @Test
    fun `a user with the admin role is admin`() {
        ManagementRepository.isAdmin("user", user("admin")) `should be equal to` true
    }

    @Test
    fun `a user with any other role is not`() {
        ManagementRepository.isAdmin("user", user("user")) `should be equal to` false
    }

    @Test
    fun `a user without a role is not`() {
        ManagementRepository.isAdmin("user", user(null)) `should be equal to` false
    }

    @Test
    fun `no user at all is not admin`() {
        ManagementRepository.isAdmin("user", null) `should be equal to` false
    }

    @Test
    fun `a legacy is_admin flag does not grant access on its own`() {
        // Access is resolved through the role system; the legacy boolean was migrated into roles
        // and must not be a second, weaker way in.
        ManagementRepository.isAdmin("user", user(role = "user", isAdmin = true)) `should be equal to` false
    }
}
