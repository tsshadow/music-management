package nl.teunschriks.mumamobile.model

import org.amshove.kluent.shouldBeEqualTo
import org.junit.Test

/**
 * Pins the branding of the single static server entry, which is the label the user sees
 * in the server list, and the pre-rebrand name that upgraded installs still carry.
 */
class ServerSettingsModelTest {

    @Test
    fun `the static server is branded MuMa`() {
        ServerSettingsModel.SERVER_NAME shouldBeEqualTo "MuMa"
    }

    @Test
    fun `the static server list has exactly one entry using the branded name`() {
        ServerSettingsModel.STATIC_SERVERS.size shouldBeEqualTo 1
        ServerSettingsModel.STATIC_SERVERS[0].name shouldBeEqualTo "MuMa"
        ServerSettingsModel.STATIC_SERVERS[0].url shouldBeEqualTo ServerSettingsModel.SERVER_URL
    }

    @Test
    fun `the legacy server name is still recognised`() {
        ServerSettingsModel.LEGACY_SERVER_NAME shouldBeEqualTo "LMS"
    }
}
