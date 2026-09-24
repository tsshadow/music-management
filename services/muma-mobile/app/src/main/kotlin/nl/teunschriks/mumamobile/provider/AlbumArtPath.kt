/*
 * AlbumArtPath.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.provider

import java.io.File

/**
 * Turns the cache key in an [AlbumArtContentProvider] URI into a file, or refuses to.
 *
 * The provider is exported (Android Auto, the media notification and the launcher's widget host
 * read it from their own processes), so any app on the phone can hand it a URI. It used to append
 * the key to the album-art directory as it came, and `../../shared_prefs/<package>_preferences.xml`
 * then opened the preferences file that holds the password and the muma API key (bug report 054).
 * Kept free of Android types so the check is testable on the plain JVM.
 */
object AlbumArtPath {

    /**
     * Whether [cacheKey] can only ever name a file directly inside the album-art directory: not
     * blank, no path separator of either kind, no `..`, no NUL. Every key the app builds itself is
     * an MD5 hex digest with a `.jpeg` suffix and passes.
     */
    fun isSafeCacheKey(cacheKey: String): Boolean = cacheKey.isNotBlank() &&
        !cacheKey.contains('/') &&
        !cacheKey.contains('\\') &&
        !cacheKey.contains("..") &&
        !cacheKey.contains('\u0000')

    /**
     * The file [cacheKey] names inside [albumArtDir], or null when the key is unsafe
     * ([isSafeCacheKey]) or its canonical path -- symlinks resolved -- is not strictly inside the
     * canonical [albumArtDir]. The file need not exist.
     */
    fun resolve(albumArtDir: File, cacheKey: String): File? {
        if (!isSafeCacheKey(cacheKey)) return null
        val root = albumArtDir.canonicalFile
        val candidate = File(root, cacheKey).canonicalFile
        return candidate.takeIf { it.path.startsWith(root.path + File.separator) }
    }
}
