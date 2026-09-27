package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.subsonic.rules.MockWebServerRule
import org.junit.Before
import org.junit.Rule

/**
 * Base class for integration tests for [SubsonicAPIClient] class.
 */
abstract class SubsonicAPIClientTest {
    @JvmField @Rule
    val mockWebServerRule = MockWebServerRule()

    protected lateinit var config: SubsonicClientConfiguration
    protected lateinit var client: SubsonicAPIClient

    @Before
    open fun setUp() {
        config = SubsonicClientConfiguration(
            baseUrl = mockWebServerRule.mockWebServer.url("/").toString(),
            username = USERNAME,
            token = TOKEN,
            minimalProtocolVersion = CLIENT_VERSION,
            clientID = CLIENT_ID
        )
        client = SubsonicAPIClient(config)
    }
}
