package nl.teunschriks.mumamobile.di

import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.CacheCleaner
import nl.teunschriks.mumamobile.util.MediaDeviceExporter
import org.koin.dsl.module

/**
 * This Koin module contains the registration of general classes needed for Ultrasonic
 */
val applicationModule = module {
    single { ActiveServerProvider() }
    single { ImageLoaderProvider() }
    single { CacheCleaner() }
    single { MediaDeviceExporter(get()) }
}
