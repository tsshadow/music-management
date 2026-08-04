@file:JvmName("RestErrorMapper")

package nl.teunschriks.mumamobile.subsonic

import android.content.Context
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.Generic
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.IncompatibleClientProtocolVersion
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.IncompatibleServerProtocolVersion
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.RequestedDataWasNotFound
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.RequiredParamMissing
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.TokenAuthNotSupportedForLDAP
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.TrialPeriodIsOver
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.UserNotAuthorizedForOperation
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.WrongUsernameOrPassword
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.MultipleConflictingAuthenticationMechanismsProvided
import nl.teunschriks.mumamobile.api.subsonic.SubsonicError.Unknown
import nl.teunschriks.mumamobile.api.subsonic.SubsonicRESTException

/**
 * Extension for [SubsonicRESTException] that returns localized error string, that can used to
 * display error reason for user.
 */
fun SubsonicRESTException.getLocalizedErrorMessage(context: Context): String = when (error) {
    is Generic -> {
        val message = (error as Generic).message
        val errorMessage = if (message == "") {
            context.getString(R.string.api_subsonic_generic_no_message)
        } else {
            message
        }
        context.getString(R.string.api_subsonic_generic, errorMessage)
    }
    RequiredParamMissing -> context.getString(R.string.api_subsonic_param_missing)
    IncompatibleClientProtocolVersion ->
        context.getString(R.string.api_subsonic_upgrade_client)
    IncompatibleServerProtocolVersion ->
        context.getString(R.string.api_subsonic_upgrade_server)
    WrongUsernameOrPassword -> context.getString(R.string.api_subsonic_not_authenticated)
    TokenAuthNotSupportedForLDAP ->
        context.getString(R.string.api_subsonic_token_auth_not_supported_for_ldap)
    UserNotAuthorizedForOperation ->
        context.getString(R.string.api_subsonic_not_authorized)
    TrialPeriodIsOver -> context.getString(R.string.api_subsonic_trial_period_is_over)
    RequestedDataWasNotFound ->
        context.getString(R.string.api_subsonic_requested_data_was_not_found)
    MultipleConflictingAuthenticationMechanismsProvided ->
        context.getString(R.string.api_subsonic_multiple_auth)
    is Unknown -> context.getString(
        R.string.api_subsonic_unknown_error,
        (error as Unknown).errorCode
    )
}
