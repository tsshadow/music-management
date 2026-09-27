@file:JvmName("MusicServiceModule")

package nl.teunschriks.mumamobile.di

import kotlin.math.abs
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIClient
import nl.teunschriks.mumamobile.api.subsonic.SubsonicAPIVersions
import nl.teunschriks.mumamobile.api.subsonic.SubsonicClientConfiguration
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.SubsonicSigning
import nl.teunschriks.mumamobile.log.TimberOkHttpLogger
import nl.teunschriks.mumamobile.service.CachedMusicService
import nl.teunschriks.mumamobile.service.FeedRepository
import nl.teunschriks.mumamobile.service.MusicService
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.service.OfflineMusicService
import nl.teunschriks.mumamobile.service.RESTMusicService
import nl.teunschriks.mumamobile.service.SubsonicTokenRefresher
import nl.teunschriks.mumamobile.util.Constants
import okhttp3.logging.HttpLoggingInterceptor
import org.koin.core.qualifier.named
import org.koin.dsl.module

/**
 * This Koin module contains the registration of classes related to the Music Services
 */
internal const val ONLINE_MUSIC_SERVICE = "OnlineMusicService"
internal const val OFFLINE_MUSIC_SERVICE = "OfflineMusicService"

val musicServiceModule = module {

    single(named("ServerInstance")) {
        return@single ActiveServerProvider.getActiveServerId()
    }

    single(named("ServerID")) {
        val serverInstance = get<Int>(named("ServerInstance"))
        val serverUrl = get<ActiveServerProvider>().getActiveServer().url
        return@single abs("$serverUrl$serverInstance".hashCode()).toString()
    }

    single {
        val server = get<ActiveServerProvider>().getActiveServer()
        val offline = server.id == ActiveServerProvider.OFFLINE_DB_ID
        // Always the Subsonic token, never the password (issue #72). When none is stored yet the
        // client obtains one from MuMa before its first request (SubsonicTokenRecoverer.obtain);
        // offline has no server to sign for.
        val token = if (offline) {
            null
        } else {
            SubsonicSigning.tokenFor(
                userName = server.userName,
                token = nl.teunschriks.mumamobile.util.SecureSettings.subsonicToken,
                tokenUser = nl.teunschriks.mumamobile.util.SecureSettings.subsonicTokenUser
            )
        }

        return@single SubsonicClientConfiguration(
            baseUrl = server.url,
            username = server.userName,
            token = token,
            apiKey = server.apiKey ?: nl.teunschriks.mumamobile.util.Settings.mumaApiKey.takeIf { it.isNotEmpty() },
            mumaUserId = server.mumaUserId ?: nl.teunschriks.mumamobile.util.Settings.mumaUserId.takeIf { it != -1 },
            minimalProtocolVersion = SubsonicAPIVersions.getClosestKnownClientApiVersion(
                server.minimumApiVersion
                    ?: Constants.REST_PROTOCOL_VERSION
            ),
            clientID = Constants.REST_CLIENT_ID,
            allowSelfSignedCertificate = server.allowSelfSignedCertificate,
            debug = BuildConfig.DEBUG,
            isRealProtocolVersion = server.minimumApiVersion != null,
            tokenStorage = nl.teunschriks.mumamobile.util.SecureSettings,
            // Fetches a missing token before the first request (issue #72), and refetches a refused
            // one and retries the request once (issue #73).
            tokenRecovery = if (offline) null else SubsonicTokenRefresher.recovery
        )
    }

    single<HttpLoggingInterceptor.Logger> { TimberOkHttpLogger() }
    single { SubsonicAPIClient(get(), get()) }

    single<MusicService>(named(ONLINE_MUSIC_SERVICE)) {
        CachedMusicService(RESTMusicService(get(), get()))
    }

    single<MusicService>(named(OFFLINE_MUSIC_SERVICE)) {
        OfflineMusicService()
    }

    // One personalized-feed repository for the whole app. The car's browse tree, the car's
    // playback callbacks and the phone's home screen all show the same two feeds, and each is a
    // pair of round trips; a repository per caller would fetch them three times and could hold
    // three different days' rankings at once. The music service is resolved per call, never
    // captured, because MusicServiceFactory swaps the instance on a server change or when the
    // network comes back.
    single {
        FeedRepository(
            mumaApiProvider = { get<SubsonicAPIClient>().mumaApi.api },
            musicServiceProvider = { MusicServiceFactory.getMusicService() }
        )
    }
}
