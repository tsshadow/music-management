package nl.teunschriks.mumamobile.api.subsonic

/**
 * Reports that the server rejected the stored credentials.
 *
 * Every API call funnels through [throwOnFailure], which is the only place that sees a
 * [SubsonicError.WrongUsernameOrPassword] regardless of which screen made the call. The app module
 * cannot be referenced from here, so it registers a [listener] instead and turns the callback into
 * whatever it needs (a return to the login screen).
 */
object AuthenticationFailureNotifier {

    /** Set once by the app module; null in tests and in the API module's own integration tests. */
    @Volatile
    var listener: ((SubsonicError) -> Unit)? = null

    /**
     * Called for every API error. Only credential rejections are forwarded: an authorization
     * error (50) means the account exists but may not do this particular thing, which is not a
     * reason to throw the user out of the app.
     */
    fun notifyIfAuthenticationFailure(error: SubsonicError) {
        if (error is SubsonicError.WrongUsernameOrPassword) {
            listener?.invoke(error)
        }
    }
}
