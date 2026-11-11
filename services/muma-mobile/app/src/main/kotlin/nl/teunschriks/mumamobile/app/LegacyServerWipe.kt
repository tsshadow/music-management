package nl.teunschriks.mumamobile.app

import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteException
import java.io.File
import timber.log.Timber

/**
 * Blanks the credentials in the legacy Room `ServerSetting` table, a leftover of the Ultrasonic
 * server list that nothing reads any more (the one server is static, see `StaticServers`, and the
 * key lives in `SecureSettings`). Opened as a plain SQLite file, not through Room, so no Room
 * migration runs for a database the app otherwise never opens.
 */
internal object LegacyServerWipe {
    /**
     * Blanks `password` (issue #101) and `apiKey` (issue #227) in [file]; skipped when the file does
     * not exist and a no-op once both are blank. The `apiKey` column came with a later migration,
     * so it is blanked in its own statement: a database without it still loses its passwords.
     * Never throws.
     */
    fun wipe(file: File) {
        if (!file.exists()) return
        try {
            SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
                run(db, "UPDATE ServerSetting SET password = '' WHERE password != ''", "passwords")
                run(db, "UPDATE ServerSetting SET apiKey = NULL WHERE apiKey IS NOT NULL", "API keys")
            }
        } catch (all: SQLiteException) {
            Timber.w("Could not open the legacy server database: %s", all.javaClass.simpleName)
        }
    }

    private fun run(db: SQLiteDatabase, sql: String, what: String) {
        try {
            db.execSQL(sql)
        } catch (all: SQLiteException) {
            Timber.w("Could not blank the legacy server %s: %s", what, all.javaClass.simpleName)
        }
    }
}
