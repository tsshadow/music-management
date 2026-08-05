package nl.teunschriks.mumamobile.log

import okhttp3.logging.HttpLoggingInterceptor
import timber.log.Timber

/**
 * Timber Logging implementation for HttpLoggingInterceptor
 */
class TimberOkHttpLogger : HttpLoggingInterceptor.Logger {
    override fun log(message: String) {
        Timber.d(message)
    }
}
