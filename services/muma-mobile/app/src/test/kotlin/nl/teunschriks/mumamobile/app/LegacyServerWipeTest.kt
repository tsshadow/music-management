package nl.teunschriks.mumamobile.app

import android.database.sqlite.SQLiteDatabase
import java.io.File
import org.amshove.kluent.`should be equal to`
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** The legacy server table loses its password and API key on start (issues #101 and #227). */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class LegacyServerWipeTest {
    @get:Rule
    val folder = TemporaryFolder()

    private fun database(withApiKey: Boolean): File {
        val file = File(folder.root, "legacy.db")
        SQLiteDatabase.openOrCreateDatabase(file, null).use { db ->
            val keyColumn = if (withApiKey) ", apiKey TEXT" else ""
            db.execSQL("CREATE TABLE ServerSetting (id INTEGER PRIMARY KEY, password TEXT NOT NULL$keyColumn)")
            val keyValue = if (withApiKey) ", 'secret-key'" else ""
            val keyName = if (withApiKey) ", apiKey" else ""
            db.execSQL("INSERT INTO ServerSetting (id, password$keyName) VALUES (1, 'secret'$keyValue)")
        }
        return file
    }

    private fun read(file: File, column: String): String? = SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY).use { db ->
        db.rawQuery("SELECT $column FROM ServerSetting WHERE id = 1", null).use { cursor ->
            cursor.moveToFirst()
            cursor.getString(0)
        }
    }

    @Test
    fun `blanks the password and the api key`() {
        val file = database(withApiKey = true)
        LegacyServerWipe.wipe(file)
        read(file, "password") `should be equal to` ""
        read(file, "apiKey") `should be equal to` null
    }

    @Test
    fun `blanks the password of a database from before the api key column`() {
        val file = database(withApiKey = false)
        LegacyServerWipe.wipe(file)
        read(file, "password") `should be equal to` ""
    }

    @Test
    fun `does nothing without a database file`() {
        val file = File(folder.root, "missing.db")
        LegacyServerWipe.wipe(file)
        file.exists() `should be equal to` false
    }
}
