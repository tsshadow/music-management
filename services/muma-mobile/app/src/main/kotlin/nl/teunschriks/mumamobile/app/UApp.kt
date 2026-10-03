package nl.teunschriks.mumamobile.app

import android.app.Application
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteException
import android.os.StrictMode
import android.os.StrictMode.ThreadPolicy
import android.os.StrictMode.VmPolicy
import io.reactivex.rxjava3.plugins.RxJavaPlugins
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.BuildConfig
import nl.teunschriks.mumamobile.api.subsonic.AuthenticationFailureNotifier
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.di.DB_FILENAME
import nl.teunschriks.mumamobile.di.appPermanentStorage
import nl.teunschriks.mumamobile.di.applicationModule
import nl.teunschriks.mumamobile.di.baseNetworkModule
import nl.teunschriks.mumamobile.di.mediaPlayerModule
import nl.teunschriks.mumamobile.di.musicServiceModule
import nl.teunschriks.mumamobile.diagnostics.CrashReportManager
import nl.teunschriks.mumamobile.log.FileLoggerTree
import nl.teunschriks.mumamobile.log.RingBufferLoggerTree
import nl.teunschriks.mumamobile.log.TimberKoinLogger
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.util.FileUtil
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Storage
import nl.teunschriks.mumamobile.util.Util
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.GlobalContext
import org.koin.core.context.startKoin
import timber.log.Timber
import timber.log.Timber.DebugTree

/**
 * The Main class of the Application
 */

class UApp : Application() {

    private var ioScope = CoroutineScope(Dispatchers.IO)

    init {
        instance = this
        if (BuildConfig.DEBUG) {
            StrictMode.setThreadPolicy(ThreadPolicy.Builder().detectAll().penaltyLog().build())
            StrictMode.setVmPolicy(VmPolicy.Builder().detectAllExceptSocket().penaltyLog().build())
        }
    }

    var initiated = false
    var isFirstRun = false
    var setupDialogDisplayed = false

    override fun onCreate() {
        initiated = true
        super.onCreate()

        if (BuildConfig.DEBUG) {
            Timber.plant(DebugTree())
        }

        RingBufferLoggerTree.plantToTimberForest()

        // None of the RxBus subscribers pass an onError handler, so any throw inside one of them
        // is rethrown by RxJava as OnErrorNotImplementedException on whichever thread is
        // delivering the event, killing the process. Log it instead.
        RxJavaPlugins.setErrorHandler { error ->
            Timber.w(error, "Undeliverable RxJava error")
        }

        Timber.d("onCreate called")

        // The API module reports credential rejections through a plain callback, because it cannot
        // see RxBus. Bridging it here (rather than in an Activity) means a rejection is noticed no
        // matter which component made the call.
        AuthenticationFailureNotifier.listener = {
            Timber.w("The server rejected the stored credentials")
            RxBus.authenticationFailurePublisher.onNext(Unit)
        }

        CrashReportManager.detectAndArmPendingReport()

        // In general we should not access the settings from the main thread to avoid blocking...
        ioScope.launch {
            // Before anything can dump the preferences: an install from before issue #101 still
            // keeps the password in plain preferences, one from before #115 the MuMa key. Readers
            // of the signed-in state run the same migration first, so the order with the media
            // session does not matter.
            ActiveServerProvider.migrateLegacyCredentials()
            wipeLegacyServerPasswords()
            if (Settings.debugLogToFile) {
                FileLoggerTree.plantToTimberForest()
                Util.dumpSettingsToLog()
            }
            // Populate externalFilesDir early
            FileUtil.cachedUltrasonicDirectory = FileUtil.ultrasonicDirectory
            Storage.mediaRoot.value
            isFirstRun = Util.isFirstRun()
        }

        if (GlobalContext.getOrNull() == null) {
            startKoin()
        }
    }

    /**
     * Blanks the `password` column of the legacy Room `ServerSetting` table, a leftover of the
     * Ultrasonic server list that nothing reads any more (the one server is static, see
     * `StaticServers`). Opened as a plain SQLite file, not through Room, so no Room migration runs
     * for a database the app otherwise never opens; skipped when the file does not exist, and a
     * no-op once the column is blank (issue #101). Never fails the start.
     */
    private fun wipeLegacyServerPasswords() {
        val file = getDatabasePath(DB_FILENAME)
        if (!file.exists()) return
        try {
            SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
                db.execSQL("UPDATE ServerSetting SET password = '' WHERE password != ''")
            }
        } catch (all: SQLiteException) {
            Timber.w("Could not blank the legacy server passwords: %s", all.javaClass.simpleName)
        }
    }

    internal fun startKoin() {
        initiated = true
        startKoin {
            // Sometimes Koin breaks when Kotlin version is upgraded,
            // you can normally fix it by changing to logger(TimberKoinLogger(Level.ERROR))
            // See https://github.com/InsertKoinIO/koin/issues/1188
            logger(TimberKoinLogger())

            // declare Android context
            androidContext(this@UApp)

            // declare modules to use
            modules(
                applicationModule,
                appPermanentStorage,
                baseNetworkModule,
                musicServiceModule,
                mediaPlayerModule
            )
        }
    }

    companion object {
        var instance: UApp? = null

        fun applicationContext(): Context = instance!!.applicationContext
    }
}

private fun VmPolicy.Builder.detectAllExceptSocket(): VmPolicy.Builder {
    detectLeakedSqlLiteObjects()
    detectActivityLeaks()
    detectLeakedClosableObjects()
    detectLeakedRegistrationObjects()
    detectFileUriExposure()
    detectContentUriWithoutPermission()
    detectCleartextNetwork()
    detectCredentialProtectedWhileLocked()
    detectUnsafeIntentLaunch()
    detectIncorrectContextUse()
    return this
}
