package nl.teunschriks.mumamobile.api.subsonic

import nl.teunschriks.mumamobile.api.subsonic.models.MusicFolder
import org.amshove.kluent.`should be equal to`
import org.junit.Test

/**
 * Integration test for [SubsonicAPIClient] for getMusicFolders() request.
 */
class SubsonicApiGetMusicFoldersTest : SubsonicAPIClientTest() {
    @Test
    fun `Should parse get music folders ok response`() {
        mockWebServerRule.enqueueResponse("get_music_folders_ok.json")

        val response = client.api.getMusicFolders().execute()

        assertResponseSuccessful(response)
        with(response.body()!!) {
            assertBaseResponseOk()
            musicFolders `should be equal to` listOf(
                MusicFolder("0", "Music"),
                MusicFolder("2", "Test")
            )
        }
    }

    @Test
    fun `Should parse get music folders error response`() {
        val response = checkErrorCallParsed(mockWebServerRule) {
            client.api.getMusicFolders().execute()
        }

        response.musicFolders `should be equal to` emptyList()
    }
}
