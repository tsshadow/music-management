package nl.teunschriks.mumamobile.di

import org.koin.dsl.module
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.CacheCleaner
import nl.teunschriks.mumamobile.util.MediaDeviceExporter

/**
 * This Koin module contains the registration of general classes needed for Ultrasonic
 */
val applicationModule = module {
    single { ActiveServerProvider(get()) }
    single { ImageLoaderProvider() }
    single { CacheCleaner() }
    single { MediaDeviceExporter(get()) }
}
