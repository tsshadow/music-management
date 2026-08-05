package nl.teunschriks.mumamobile.di

import org.koin.dsl.module
import nl.teunschriks.mumamobile.activity.NavigationActivity
import nl.teunschriks.mumamobile.service.ExternalStorageMonitor
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.PlaybackStateSerializer
import nl.teunschriks.mumamobile.subsonic.NetworkAndStorageChecker
import nl.teunschriks.mumamobile.subsonic.ShareHandler

/**
 * This Koin module contains the registration of classes related to the media player
 */
val mediaPlayerModule = module {

    // These are dependency-free
    single { PlaybackStateSerializer() }
    single { ExternalStorageMonitor() }
    single { NetworkAndStorageChecker() }
    single { ShareHandler() }

    scope<NavigationActivity> {
        scoped { MediaPlayerManager(get(), get()) }
        scoped { MediaPlayerLifecycleSupport(get(), get(), get(), get()) }
    }
}
