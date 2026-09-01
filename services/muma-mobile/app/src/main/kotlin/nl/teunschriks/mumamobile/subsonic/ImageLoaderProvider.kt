/*
 * ImageLoaderProvider.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.subsonic

import androidx.core.content.res.ResourcesCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.imageloader.ImageLoader
import nl.teunschriks.mumamobile.imageloader.ImageLoaderConfig
import nl.teunschriks.mumamobile.util.CoroutinePatterns
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Util
import org.koin.core.component.KoinComponent
import org.koin.core.component.get
import org.koin.core.qualifier.named
import timber.log.Timber

/**
 * Handles the lifetime of the Image Loader
 */
class ImageLoaderProvider :
    KoinComponent,
    CoroutineScope by CoroutineScope(Dispatchers.IO) {
    private var imageLoader: ImageLoader? = null
    private var serverID: String = get(named("ServerID"))

    @Synchronized
    fun clearImageLoader() {
        imageLoader = null
    }

    init {
        Timber.d("Prepping Loader")
        // Populate the ImageLoader async & early
        launch {
            getImageLoader()
        }
    }

    @Synchronized
    fun getImageLoader(): ImageLoader {
        // We need to generate a new ImageLoader if the server has changed...
        val currentID = get<String>(named("ServerID"))
        if (imageLoader == null || currentID != serverID) {
            imageLoader = ImageLoader(UApp.applicationContext(), get(), config)
            serverID = currentID

            launch {
                FileUtil.ensureAlbumArtDirectory()
            }
        }

        return imageLoader!!
    }

    fun executeOn(cb: (iL: ImageLoader) -> Unit) {
        launch(CoroutinePatterns.loggingExceptionHandler) {
            val iL = getImageLoader()
            withContext(Dispatchers.Main) {
                cb(iL)
            }
        }
    }

    companion object {
        val config by lazy {
            var defaultSize = 0
            val fallbackImage = ResourcesCompat.getDrawable(
                UApp.applicationContext().resources,
                R.drawable.unknown_album,
                null
            )

            // Determine the density-dependent image sizes by taking the fallback album
            // image and querying its size.
            if (fallbackImage != null) {
                defaultSize = fallbackImage.intrinsicHeight
            }

            ImageLoaderConfig(
                Util.getMaxDisplayMetric(),
                defaultSize,
                FileUtil.albumArtDirectory
            )
        }
    }
}
