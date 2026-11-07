/*
 * StationLogoProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
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
import java.io.File
import java.io.IOException
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.app.UApp
import timber.log.Timber

/**
 * Serves the logos of the live stations to the car.
 *
 * The logos ship in the web bundle inside the APK. Android Auto reads artwork from its own process
 * through the content resolver, so it cannot read an asset of this app: the provider copies the
 * file to the cache once per app version, and serves that copy.
 */
class StationLogoProvider : ContentProvider() {

    companion object {
        private const val ASSET_DIR = "public/images/stations"
        private val SLUG = Regex("[a-z0-9-]+")

        private val slugsWithLogo: Set<String> by lazy {
            val files = try {
                UApp.applicationContext().assets.list(ASSET_DIR).orEmpty()
            } catch (e: IOException) {
                Timber.w(e, "Could not list the station logos")
                emptyArray()
            }
            files.map { it.removeSuffix(".png") }.toSet()
        }

        private fun authority(): String = UApp.applicationContext().packageName + ".provider.StationLogoProvider"

        /** The address of the logo, or null for a station a curator added: that one has no file. */
        fun artUri(slug: String): Uri? {
            if (slug !in slugsWithLogo) return null

            return Uri.Builder()
                .scheme(ContentResolver.SCHEME_CONTENT)
                .authority(authority())
                .appendPath(slug)
                .build()
        }

        /** The slug in a URI, or null. The URI comes from another process, so it is not trusted. */
        fun slugOf(uri: Uri): String? = uri.pathSegments.singleOrNull()?.takeIf { SLUG.matches(it) }
    }

    override fun onCreate(): Boolean = true

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor? {
        val slug = slugOf(uri) ?: return null
        val dir = File(UApp.applicationContext().cacheDir, "station-logos-${BuildConfig.VERSION_CODE}").apply { mkdirs() }
        val file = File(dir, "$slug.png")

        if (!file.exists()) {
            try {
                UApp.applicationContext().assets.open("$ASSET_DIR/$slug.png").use { input ->
                    // A temporary name first: the car may read the file while this runs.
                    val partial = File(dir, "$slug.part")
                    partial.outputStream().use { input.copyTo(it) }
                    partial.renameTo(file)
                }
            } catch (e: IOException) {
                Timber.w(e, "No logo for station %s", slug)
                return null
            }
        }

        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    }

    override fun getType(uri: Uri): String = "image/png"

    override fun getStreamTypes(uri: Uri, mimeTypeFilter: String): Array<String> = arrayOf("image/png")

    override fun query(
        uri: Uri,
        projection: Array<out String>?,
        selection: String?,
        selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor? = null

    override fun insert(uri: Uri, values: ContentValues?): Uri? = null

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0

    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int = 0
}
