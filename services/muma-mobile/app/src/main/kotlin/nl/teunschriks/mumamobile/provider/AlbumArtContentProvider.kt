/*
 * AlbumArtContentProvider.kt
 * Copyright (C) 2009-2022 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.provider

import android.content.ContentProvider
import android.content.ContentResolver
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.util.Locale
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.imageloader.redactCredentials
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.FileUtil
import org.koin.core.component.KoinComponent
import org.koin.core.component.inject
import timber.log.Timber

/**
 * Serves cached cover art to readers in other processes (Android Auto, the media notification,
 * the home-screen widget) under `content://<package>.provider.AlbumArtContentProvider/<coverArt>|<cacheKey>`,
 * fetching the picture into the cache first when it is missing. Read-only, and limited to the
 * album-art cache directory by [AlbumArtPath].
 */
class AlbumArtContentProvider :
    ContentProvider(),
    KoinComponent {

    private val imageLoaderProvider: ImageLoaderProvider by inject()

    companion object {
        fun mapArtworkToContentProviderUri(track: Track?): Uri? {
            if (track?.coverArt.isNullOrBlank()) return null
            return mapArtworkToContentProviderUri(track.coverArt, FileUtil.getAlbumArtKey(track, true))
        }

        fun mapArtworkToContentProviderUri(coverArt: String?, cacheKey: String?): Uri? {
            if (coverArt.isNullOrBlank() || cacheKey.isNullOrBlank()) return null
            val domain = UApp.applicationContext().packageName + ".provider.AlbumArtContentProvider"
            return Uri.Builder()
                .scheme(ContentResolver.SCHEME_CONTENT)
                .authority(domain)
                .path(String.format(Locale.ROOT, "%s|%s", coverArt, cacheKey))
                .build()
        }
    }

    override fun onCreate(): Boolean {
        Timber.i("AlbumArtContentProvider.onCreate called")
        return true
    }

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor? {
        val parts = uri.path?.trim('/')?.split('|')
        if (parts?.count() != 2 || parts[0].isEmpty() || parts[1].isEmpty()) return null

        // Any app can call an exported provider: a key that could leave the album-art directory
        // is refused before it is used for anything (see AlbumArtPath).
        val resolved = AlbumArtPath.resolve(FileUtil.albumArtDirectory, parts[1])
        if (resolved == null) {
            Timber.w("AlbumArtContentProvider refused a cache key outside the album-art directory")
            return null
        }
        val albumArtFile = resolved.path
        Timber.d("AlbumArtContentProvider openFile id: %s; file: %s", redactCredentials(parts[0]), albumArtFile)

        // TODO: Check if the dependency on the image loader could be removed.
        // TODO: This method can be called outside of our regular lifecycle, where Koin might not exist yet
        imageLoaderProvider.executeOn {
            it.downloadCoverArt(parts[0], albumArtFile)
        }
        if (!resolved.exists()) return null

        return ParcelFileDescriptor.open(resolved, ParcelFileDescriptor.MODE_READ_ONLY)
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null

    override fun query(
        uri: Uri,
        projection: Array<String>?,
        selection: String?,
        selectionArgs: Array<String>?,
        sortOrder: String?
    ): Cursor? = null

    override fun update(
        uri: Uri,
        values: ContentValues?,
        selection: String?,
        selectionArgs: Array<String>?
    ) = 0

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<String>?) = 0

    override fun getType(uri: Uri): String? = null

    override fun getStreamTypes(uri: Uri, mimeTypeFilter: String): Array<String> = arrayOf("image/jpeg", "image/png", "image/gif")
}
