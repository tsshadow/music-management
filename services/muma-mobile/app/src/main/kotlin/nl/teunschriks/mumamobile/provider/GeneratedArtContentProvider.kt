/*
 * GeneratedArtContentProvider.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.provider

import android.content.ContentProvider
import android.content.ContentResolver
import android.content.ContentValues
import android.database.Cursor
import android.graphics.Bitmap
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.File
import java.io.FileOutputStream
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.coverart.PlaylistArtKind
import nl.teunschriks.mumamobile.coverart.PlaylistArtRenderer
import timber.log.Timber

/**
 * Serves the covers the app draws for the things that have none.
 *
 * Android Auto loads artwork in its own process through the content resolver, so a bitmap held in
 * this one is unreachable: it has to become a file behind a `content://` URI. Everything the
 * renderer needs therefore travels in the URI, the colour included -- the car has no other way of
 * learning it.
 *
 * Separate from [AlbumArtContentProvider] on purpose. That one fetches a picture that exists on
 * the server and caches it; this one renders a picture that exists nowhere. Sharing an authority
 * would mean one `openFile` deciding between the two on the shape of a path.
 */
class GeneratedArtContentProvider : ContentProvider() {

    /** What a URI asks for. */
    data class Request(val kind: PlaylistArtKind, val title: String, val tint: Int)

    companion object {
        /** The size the tile is rendered at: enough for a car screen, cheap enough to draw. */
        private const val RENDER_SIZE = 512

        private fun authority(): String = UApp.applicationContext().packageName + ".provider.GeneratedArtContentProvider"

        /**
         * The address for one generated cover, or null when there is nothing to draw.
         *
         * A blank name gets no URI rather than a blank tile: an item without artwork keeps the
         * list layout, which is the honest answer for something that has no name either.
         */
        fun artUri(kind: PlaylistArtKind, title: String, tint: Int): Uri? {
            if (title.isBlank()) return null

            return Uri.Builder()
                .scheme(ContentResolver.SCHEME_CONTENT)
                .authority(authority())
                .appendPath(kind.name.lowercase())
                .appendPath(tint.toString())
                .appendPath(title)
                .build()
        }

        /**
         * What a URI asks for, or null when it asks for something this provider does not draw.
         *
         * Nothing here trusts the URI: it arrives from another process, and a kind that does not
         * exist or a colour that is not a number is a refusal rather than a guess.
         */
        fun parse(uri: Uri): Request? {
            val segments = uri.pathSegments
            if (segments.size != 3) return null

            val kind = PlaylistArtKind.entries.firstOrNull { it.name.equals(segments[0], ignoreCase = true) }
                ?: return null
            val tint = segments[1].toIntOrNull() ?: return null
            val title = segments[2]
            if (title.isBlank()) return null

            return Request(kind, title, tint)
        }
    }

    override fun onCreate(): Boolean = true

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor? {
        val request = parse(uri) ?: return null
        val file = cacheFile(request)

        if (!file.exists()) {
            try {
                render(request, file)
            } catch (e: java.io.IOException) {
                Timber.w(e, "Could not write generated art for %s", request.title)
                return null
            }
        }

        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    }

    private fun cacheFile(request: Request): File {
        val dir = File(UApp.applicationContext().cacheDir, "generated-art").apply { mkdirs() }
        return File(dir, PlaylistArtRenderer.cacheKey(request.kind, request.title, request.tint) + ".png")
    }

    private fun render(request: Request, file: File) {
        val art = PlaylistArtRenderer.render(request.kind, request.title, request.tint, RENDER_SIZE)
        // Written to a temporary name first: the car may open the file while this runs, and half
        // a PNG reads as a broken image rather than as one still being drawn.
        val partial = File(file.parentFile, file.name + ".part")
        FileOutputStream(partial).use { art.compress(Bitmap.CompressFormat.PNG, 100, it) }
        partial.renameTo(file)
    }

    override fun getType(uri: Uri): String = "image/png"

    override fun getStreamTypes(uri: Uri, mimeTypeFilter: String): Array<String> = arrayOf("image/png")

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
}
