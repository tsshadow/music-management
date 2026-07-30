/*
 * EditServerFragment.kt
 * Copyright (C) 2009-2023 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package org.moire.ultrasonic.fragment

import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.google.android.libraries.identity.googleid.GoogleIdTokenParsingException
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputLayout
import com.skydoves.colorpickerview.ColorPickerDialog
import com.skydoves.colorpickerview.flag.BubbleFlag
import com.skydoves.colorpickerview.flag.FlagMode
import com.skydoves.colorpickerview.listeners.ColorEnvelopeListener
import java.net.MalformedURLException
import java.net.URL
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.koin.android.ext.android.inject
import org.koin.androidx.viewmodel.ext.android.viewModel
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.subsonic.SubsonicAPIClient
import org.moire.ultrasonic.data.ActiveServerProvider
import org.moire.ultrasonic.data.ServerSetting
import org.moire.ultrasonic.model.EditServerModel
import org.moire.ultrasonic.model.ServerSettingsModel
import org.moire.ultrasonic.service.MusicServiceFactory
import org.moire.ultrasonic.util.CommunicationError.getErrorMessage
import org.moire.ultrasonic.util.ErrorDialog
import org.moire.ultrasonic.util.InfoDialog
import org.moire.ultrasonic.util.ServerColor
import org.moire.ultrasonic.util.Util
import org.moire.ultrasonic.util.Util.toast
import timber.log.Timber

private const val DIALOG_PADDING = 12

/**
 * Displays a form where server settings can be created / edited
 */
class EditServerFragment : Fragment() {

    private val serverSettingsModel: ServerSettingsModel by viewModel()
    private val activeServerProvider: ActiveServerProvider by inject()
    private val subsonicAPIClient: SubsonicAPIClient by inject()

    private var currentServerSetting: ServerSetting? = null

    private var serverNameEditText: TextInputLayout? = null
    private var serverAddressEditText: TextInputLayout? = null
    private var serverColorImageView: ImageView? = null
    private var userNameEditText: TextInputLayout? = null
    private var passwordEditText: TextInputLayout? = null
    private var apiKeyEditText: TextInputLayout? = null
    private var mumaUserIdEditText: TextInputLayout? = null
    private var selfSignedSwitch: SwitchMaterial? = null
    private var plaintextSwitch: SwitchMaterial? = null
    private var jukeboxSwitch: SwitchMaterial? = null
    private var saveButton: Button? = null
    private var testButton: Button? = null
    private var cancelButton: Button? = null
    private var googleSignInButton: Button? = null
    private var isInstanceStateSaved: Boolean = false
    private var currentColor: Int = 0
    private var selectedColor: Int? = null

    private val navArgs by navArgs<EditServerFragmentArgs>()
    val model: EditServerModel by viewModels()

    @Override
    override fun onCreate(savedInstanceState: Bundle?) {
        Util.applyTheme(this.context)
        super.onCreate(savedInstanceState)
    }

    override fun onAttach(context: Context) {
        requireActivity().onBackPressedDispatcher.addCallback(
            this,
            confirmCloseCallback
        )
        super.onAttach(context)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? = inflater.inflate(R.layout.server_edit, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        serverNameEditText = view.findViewById(R.id.edit_server_name)
        serverAddressEditText = view.findViewById(R.id.edit_server_address)
        serverColorImageView = view.findViewById(R.id.edit_server_color_picker)
        userNameEditText = view.findViewById(R.id.edit_server_username)
        passwordEditText = view.findViewById(R.id.edit_server_password)
        apiKeyEditText = view.findViewById(R.id.edit_server_apikey)
        mumaUserIdEditText = view.findViewById(R.id.edit_server_muma_userid)
        selfSignedSwitch = view.findViewById(R.id.edit_self_signed)
        plaintextSwitch = view.findViewById(R.id.edit_plaintext)
        jukeboxSwitch = view.findViewById(R.id.edit_jukebox)
        saveButton = view.findViewById(R.id.edit_save)
        testButton = view.findViewById(R.id.edit_test)
        cancelButton = view.findViewById(R.id.edit_cancel)
        googleSignInButton = view.findViewById(R.id.google_signin_button)

        if (navArgs.index != -1) {
            // Editing an existing server
            FragmentTitle.setTitle(this, R.string.server_editor_label)

            // Disable fields for the static LMS server
            if (navArgs.index == 0) {
                serverNameEditText?.isEnabled = false
                serverAddressEditText?.isEnabled = false
                serverColorImageView?.isEnabled = false
                apiKeyEditText?.isEnabled = false
                mumaUserIdEditText?.isEnabled = false
                selfSignedSwitch?.isEnabled = false
                plaintextSwitch?.isEnabled = false
                jukeboxSwitch?.isEnabled = false
            }

            val serverSetting = serverSettingsModel.getServerSetting(navArgs.index)
            serverSetting.observe(
                viewLifecycleOwner
            ) { t ->
                if (t != null) {
                    currentServerSetting = t
                    if (!isInstanceStateSaved) setFields()
                    // Remove the minimum API version so it can be detected again
                    if (currentServerSetting?.minimumApiVersion != null) {
                        currentServerSetting!!.minimumApiVersion = null
                        viewLifecycleOwner.lifecycleScope.launch {
                            serverSettingsModel.updateItem(currentServerSetting)
                            if (
                                activeServerProvider.getActiveServer().id ==
                                currentServerSetting!!.id
                            ) {
                                MusicServiceFactory.resetMusicService()
                            }
                        }
                    }
                }
            }
            saveButton!!.setOnClickListener {
                if (currentServerSetting != null) {
                    if (getFields()) {
                        viewLifecycleOwner.lifecycleScope.launch {
                            serverSettingsModel.updateItem(currentServerSetting)
                            // Apply modifications if the current server was modified
                            if (
                                activeServerProvider.getActiveServer().id ==
                                currentServerSetting!!.id
                            ) {
                                MusicServiceFactory.resetMusicService()
                            }
                            findNavController().navigateUp()
                        }
                    }
                }
            }
        } else {
            // Creating a new server
            FragmentTitle.setTitle(this, R.string.server_editor_new_label)
            updateColor(null)
            currentServerSetting = ServerSetting()
            saveButton!!.setOnClickListener {
                if (getFields()) {
                    viewLifecycleOwner.lifecycleScope.launch {
                        serverSettingsModel.saveNewItem(currentServerSetting)
                        findNavController().navigateUp()
                    }
                }
            }
        }

        testButton!!.setOnClickListener {
            if (getFields()) {
                testConnection()
            }
        }

        cancelButton!!.setOnClickListener {
            finishActivity()
        }

        googleSignInButton!!.setOnClickListener {
            startGoogleSignIn()
        }

        serverColorImageView!!.setOnClickListener {
            val bubbleFlag = BubbleFlag(context)
            bubbleFlag.flagMode = FlagMode.LAST
            ColorPickerDialog.Builder(context).apply {
                this.colorPickerView.setInitialColor(currentColor)
                this.colorPickerView.flagView = bubbleFlag
            }
                .attachAlphaSlideBar(false)
                .setPositiveButton(
                    getString(R.string.common_ok),
                    ColorEnvelopeListener { envelope, _ ->
                        selectedColor = envelope.color
                        updateColor(envelope.color)
                    }
                )
                .setNegativeButton(getString(R.string.common_cancel)) { dialogInterface, _ ->
                    dialogInterface.dismiss()
                }
                .setBottomSpace(DIALOG_PADDING)
                .show()
        }

        serverAddressEditText?.editText?.setOnFocusChangeListener { _, hasFocus ->
            if (!hasFocus) correctServerAddress()
        }
    }

    private val confirmCloseCallback = object : OnBackPressedCallback(
        // default to enabled
        true
    ) {
        override fun handleOnBackPressed() {
            finishActivity()
        }
    }

    override fun onStop() {
        Util.hideKeyboard(activity)
        confirmCloseCallback.isEnabled = false
        super.onStop()
    }

    override fun onResume() {
        confirmCloseCallback.isEnabled = true
        super.onResume()
    }

    private fun correctServerAddress() {
        serverAddressEditText?.editText?.setText(
            serverAddressEditText?.editText?.text?.trim(' ', '/')
        )
    }

    private fun updateColor(color: Int?) {
        val image = ContextCompat.getDrawable(requireContext(), R.drawable.thumb_drawable)
        currentColor = color ?: ServerColor.getBackgroundColor(requireContext(), null)
        image?.setTint(currentColor)
        serverColorImageView?.background = image
    }
    override fun onSaveInstanceState(savedInstanceState: Bundle) {
        savedInstanceState.putString(
            ::serverNameEditText.name,
            serverNameEditText!!.editText?.text.toString()
        )
        savedInstanceState.putString(
            ::serverAddressEditText.name,
            serverAddressEditText!!.editText?.text.toString()
        )
        savedInstanceState.putString(
            ::userNameEditText.name,
            userNameEditText!!.editText?.text.toString()
        )
        savedInstanceState.putString(
            ::passwordEditText.name,
            passwordEditText!!.editText?.text.toString()
        )
        savedInstanceState.putString(
            ::apiKeyEditText.name,
            apiKeyEditText!!.editText?.text.toString()
        )
        savedInstanceState.putString(
            ::mumaUserIdEditText.name,
            mumaUserIdEditText!!.editText?.text.toString()
        )
        savedInstanceState.putBoolean(
            ::selfSignedSwitch.name,
            selfSignedSwitch!!.isChecked
        )
        savedInstanceState.putBoolean(
            ::plaintextSwitch.name,
            plaintextSwitch!!.isChecked
        )
        savedInstanceState.putBoolean(
            ::jukeboxSwitch.name,
            jukeboxSwitch!!.isChecked
        )
        savedInstanceState.putInt(
            ::serverColorImageView.name,
            currentColor
        )
        if (selectedColor != null) {
            savedInstanceState.putInt(
                ::selectedColor.name,
                selectedColor!!
            )
        }
        savedInstanceState.putBoolean(
            ::isInstanceStateSaved.name,
            true
        )

        super.onSaveInstanceState(savedInstanceState)
    }

    override fun onViewStateRestored(savedInstanceState: Bundle?) {
        super.onViewStateRestored(savedInstanceState)

        if (savedInstanceState == null) return

        serverNameEditText!!.editText?.setText(
            savedInstanceState.getString(::serverNameEditText.name)
        )
        serverAddressEditText!!.editText?.setText(
            savedInstanceState.getString(::serverAddressEditText.name)
        )
        userNameEditText!!.editText?.setText(
            savedInstanceState.getString(::userNameEditText.name)
        )
        passwordEditText!!.editText?.setText(
            savedInstanceState.getString(::passwordEditText.name)
        )
        apiKeyEditText!!.editText?.setText(
            savedInstanceState.getString(::apiKeyEditText.name)
        )
        mumaUserIdEditText!!.editText?.setText(
            savedInstanceState.getString(::mumaUserIdEditText.name)
        )
        selfSignedSwitch!!.isChecked = savedInstanceState.getBoolean(::selfSignedSwitch.name)
        plaintextSwitch!!.isChecked = savedInstanceState.getBoolean(::plaintextSwitch.name)
        jukeboxSwitch!!.isChecked = savedInstanceState.getBoolean(::jukeboxSwitch.name)
        updateColor(savedInstanceState.getInt(::serverColorImageView.name))
        if (savedInstanceState.containsKey(::selectedColor.name)) {
            selectedColor = savedInstanceState.getInt(::selectedColor.name)
        }
        isInstanceStateSaved = savedInstanceState.getBoolean(::isInstanceStateSaved.name)
    }

    /**
     * Sets the values of the Form from the current Server Setting instance
     */
    private fun setFields() {
        if (currentServerSetting == null) return

        serverNameEditText!!.editText?.setText(currentServerSetting!!.name)
        serverAddressEditText!!.editText?.setText(currentServerSetting!!.url)
        userNameEditText!!.editText?.setText(currentServerSetting!!.userName)
        passwordEditText!!.editText?.setText(currentServerSetting!!.password)
        apiKeyEditText!!.editText?.setText(currentServerSetting!!.apiKey)
        mumaUserIdEditText!!.editText?.setText(currentServerSetting!!.mumaUserId?.toString() ?: "")
        selfSignedSwitch!!.isChecked = currentServerSetting!!.allowSelfSignedCertificate
        plaintextSwitch!!.isChecked = currentServerSetting!!.forcePlainTextPassword
        jukeboxSwitch!!.isChecked = currentServerSetting!!.jukeboxByDefault
        updateColor(currentServerSetting!!.color)
    }

    /**
     * Retrieves the values in the Form to the current Server Setting instance
     * This function also does some basic validation on the fields
     */
    private fun getFields(): Boolean {
        if (currentServerSetting == null) return false
        var isValid = true
        var url: URL? = null

        if (serverAddressEditText!!.editText?.text.isNullOrBlank()) {
            serverAddressEditText!!.error = getString(R.string.server_editor_required)
            isValid = false
        } else {
            try {
                correctServerAddress()
                val urlString = serverAddressEditText!!.editText?.text.toString()
                url = URL(urlString)
                if (
                    urlString != urlString.trim(' ') ||
                    url.host.isNullOrBlank()
                ) {
                    throw MalformedURLException()
                }
                serverAddressEditText!!.error = null
            } catch (exception: MalformedURLException) {
                serverAddressEditText!!.error = getString(R.string.settings_invalid_url)
                isValid = false
            }
        }

        if (serverNameEditText!!.editText?.text.isNullOrBlank()) {
            if (isValid && url != null) {
                serverNameEditText!!.editText?.setText(url.host)
            }
        }

        if (userNameEditText!!.editText?.text.isNullOrBlank()) {
            userNameEditText!!.error = getString(R.string.server_editor_required)
            isValid = false
        } else {
            userNameEditText!!.error = null
        }

        if (isValid) {
            currentServerSetting!!.name = serverNameEditText!!.editText?.text.toString()
            currentServerSetting!!.url = serverAddressEditText!!.editText?.text.toString()
            currentServerSetting!!.color = selectedColor ?: currentColor
            currentServerSetting!!.userName = userNameEditText!!.editText?.text.toString()
            currentServerSetting!!.password = passwordEditText!!.editText?.text.toString()
            currentServerSetting!!.apiKey = apiKeyEditText!!.editText?.text.toString().takeIf { it.isNotBlank() }
            currentServerSetting!!.mumaUserId =
                mumaUserIdEditText!!.editText?.text.toString().toIntOrNull()
            currentServerSetting!!.allowSelfSignedCertificate = selfSignedSwitch!!.isChecked
            currentServerSetting!!.forcePlainTextPassword = plaintextSwitch!!.isChecked
            currentServerSetting!!.jukeboxByDefault = jukeboxSwitch!!.isChecked
        }

        return isValid
    }

    /**
     * Checks whether any value in the fields are changed according to their original values.
     */
    private fun areFieldsChanged(): Boolean {
        if (currentServerSetting == null || currentServerSetting!!.id == 0) {
            return serverNameEditText!!.editText?.text!!.isNotBlank() ||
                serverAddressEditText!!.editText?.text.toString() != "http://" ||
                userNameEditText!!.editText?.text!!.isNotBlank() ||
                passwordEditText!!.editText?.text!!.isNotBlank() ||
                apiKeyEditText!!.editText?.text!!.isNotBlank() ||
                mumaUserIdEditText!!.editText?.text!!.isNotBlank()
        }

        return currentServerSetting!!.name != serverNameEditText!!.editText?.text.toString() ||
            currentServerSetting!!.url != serverAddressEditText!!.editText?.text.toString() ||
            currentServerSetting!!.userName != userNameEditText!!.editText?.text.toString() ||
            currentServerSetting!!.password != passwordEditText!!.editText?.text.toString() ||
            (currentServerSetting!!.apiKey ?: "") != apiKeyEditText!!.editText?.text.toString() ||
            currentServerSetting!!.mumaUserId !=
            mumaUserIdEditText!!.editText?.text.toString().toIntOrNull() ||
            currentServerSetting!!.allowSelfSignedCertificate != selfSignedSwitch!!.isChecked ||
            currentServerSetting!!.forcePlainTextPassword != plaintextSwitch!!.isChecked ||
            currentServerSetting!!.jukeboxByDefault != jukeboxSwitch!!.isChecked
    }

    /**
     * Tests if the network connection to the entered Server Settings can be made
     */
    @Suppress("TooGenericExceptionCaught")
    private fun testConnection() {
        val testSetting = ServerSetting()
        val builder = InfoDialog.Builder(requireContext())
        builder.setTitle(R.string.supported_server_features)
        builder.setMessage("${currentServerSetting!!.url}\n\n${getProgress(testSetting)}")
        val dialog: AlertDialog = builder.create()
        dialog.show()

        val testJob = lifecycleScope.launch {
            try {
                val flow = model.queryFeatureSupport(currentServerSetting!!).flowOn(Dispatchers.IO)

                flow.collect {
                    model.storeFeatureSupport(testSetting, it)
                    if (it.type == EditServerModel.Companion.ServerFeature.MUMA && it.supported) {
                        if (currentServerSetting!!.apiKey.isNullOrBlank()) {
                            currentServerSetting!!.apiKey = it.apiKey
                            currentServerSetting!!.mumaUserId = it.userId
                            withContext(Dispatchers.Main) {
                                apiKeyEditText!!.editText?.setText(it.apiKey)
                                mumaUserIdEditText!!.editText?.setText(it.userId?.toString())
                            }
                        }
                    }
                    dialog.setMessage("${currentServerSetting!!.url}\n\n${getProgress(testSetting)}")
                    Timber.w("${it.type} support: ${it.supported}")
                }

                currentServerSetting!!.chatSupport = testSetting.chatSupport
                currentServerSetting!!.bookmarkSupport = testSetting.bookmarkSupport
                currentServerSetting!!.shareSupport = testSetting.shareSupport
                currentServerSetting!!.podcastSupport = testSetting.podcastSupport
                currentServerSetting!!.videoSupport = testSetting.videoSupport
                currentServerSetting!!.jukeboxSupport = testSetting.jukeboxSupport
            } catch (cancellationException: CancellationException) {
                Timber.i(cancellationException)
            } catch (exception: Exception) {
                dialog.dismiss()
                Timber.w(exception)
                ErrorDialog.Builder(requireContext())
                    .setTitle(R.string.error_label)
                    .setMessage(getErrorMessage(exception))
                    .show()
            }
        }

        dialog.setOnDismissListener { testJob.cancel() }
    }

    private fun getProgress(serverSetting: ServerSetting): String {
        val isAnyDisabled = arrayOf(
            serverSetting.chatSupport,
            serverSetting.bookmarkSupport,
            serverSetting.shareSupport,
            serverSetting.podcastSupport,
            serverSetting.videoSupport,
            serverSetting.jukeboxSupport,
            if (serverSetting.apiKey != null) true else null
        ).any { x -> x == false }

        var progressString = String.format(
            """
                    |%s - ${resources.getString(R.string.button_bar_chat)}
                    |%s - ${resources.getString(R.string.button_bar_bookmarks)}
                    |%s - ${resources.getString(R.string.button_bar_shares)}
                    |%s - ${resources.getString(R.string.button_bar_podcasts)}
                    |%s - ${resources.getString(R.string.main_videos)}
                    |%s - ${resources.getString(R.string.jukebox)}
                    |%s - MuMa
            """.trimMargin(),
            boolToMark(serverSetting.chatSupport),
            boolToMark(serverSetting.bookmarkSupport),
            boolToMark(serverSetting.shareSupport),
            boolToMark(serverSetting.podcastSupport),
            boolToMark(serverSetting.videoSupport),
            boolToMark(serverSetting.jukeboxSupport),
            boolToMark(if (serverSetting.apiKey != null) true else null)
        )
        if (isAnyDisabled) {
            progressString += "\n\n" + resources.getString(R.string.server_editor_disabled_feature)
        }

        return progressString
    }

    private fun boolToMark(value: Boolean?): String {
        if (value == null) {
            return "⌛"
        }
        return if (value) "✔️" else "❌"
    }

    /**
     * Finishes the Activity, after confirmation from the user if needed
     */
    private fun finishActivity() {
        if (areFieldsChanged()) {
            ErrorDialog.Builder(requireContext())
                .setTitle(R.string.common_confirm)
                .setMessage(R.string.server_editor_leave_confirmation)
                .setPositiveButton(R.string.common_ok) { dialog, _ ->
                    dialog.dismiss()
                    findNavController().navigateUp()
                }
                .setNegativeButton(R.string.common_cancel) { dialog, _ ->
                    dialog.dismiss()
                }
                .show()
        } else {
            findNavController().navigateUp()
        }
    }

    private fun startGoogleSignIn() {
        if (org.moire.ultrasonic.BuildConfig.GOOGLE_WEB_CLIENT_ID == "placeholder-id") {
            Timber.e("GOOGLE_WEB_CLIENT_ID is not configured! Google Sign-In will fail.")
        }
        val credentialManager = CredentialManager.create(requireContext())
        // GetGoogleIdOption (even with setFilterByAuthorizedAccounts(false)) only reliably
        // surfaces a credential for accounts that have already signed into this app before -
        // for a first-time sign-in it throws NoCredentialException regardless of the device
        // having a real, usable Google account. GetSignInWithGoogleOption is Google's dedicated
        // option for this "not yet authorized" case and always shows the account chooser.
        val googleIdTokenRequest = GetSignInWithGoogleOption
            .Builder(org.moire.ultrasonic.BuildConfig.GOOGLE_WEB_CLIENT_ID)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdTokenRequest)
            .build()

        lifecycleScope.launch {
            try {
                val result = credentialManager.getCredential(
                    requireContext(),
                    request
                )
                handleGoogleSignInResult(result.credential)
            } catch (e: GetCredentialCancellationException) {
                // Do nothing
            } catch (e: NoCredentialException) {
                Timber.e(e, "Google Sign-In failed: No credentials available")
                toast(R.string.google_signin_no_accounts)
            } catch (e: Exception) {
                Timber.e(e, "Google Sign-In failed")
                toast(R.string.background_task_network_error)
            }
        }
    }

    private fun handleGoogleSignInResult(credential: androidx.credentials.Credential) {
        // Credential Manager always returns third-party credential types (like Google's) as a
        // generic CustomCredential over the IPC boundary - it is never delivered as the concrete
        // GoogleIdTokenCredential subclass, even though that class extends CustomCredential
        // locally. It must be parsed explicitly via createFrom().
        if (
            credential is CustomCredential &&
            credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
        ) {
            val idToken = try {
                GoogleIdTokenCredential.createFrom(credential.data).idToken
            } catch (e: GoogleIdTokenParsingException) {
                Timber.e(e, "Failed to parse Google ID token credential")
                toast(R.string.background_task_network_error)
                return
            }
            performMumaGoogleAuth(idToken)
        } else {
            Timber.e("Google Sign-In returned an unexpected credential type: ${credential.javaClass.name}")
            toast(R.string.background_task_network_error)
        }
    }

    private fun performMumaGoogleAuth(idToken: String) {
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val mumaApi = subsonicAPIClient.mumaApi?.api
                    val response = mumaApi?.googleAuth(org.moire.ultrasonic.api.muma.GoogleAuthRequest(idToken))?.execute()
                    if (response?.isSuccessful == true) {
                        response.body()
                    } else {
                        null
                    }
                } catch (e: Exception) {
                    Timber.e(e, "MuMa Google Auth failed")
                    null
                }
            }

            if (result != null) {
                when (result.status) {
                    "ok" -> {
                        // Logged in!
                        org.moire.ultrasonic.util.SecureSettings.mumaAccessToken = result.access_token ?: result.api_key
                        org.moire.ultrasonic.util.SecureSettings.mumaRefreshToken = result.refresh_token
                        result.user?.id?.let {
                            org.moire.ultrasonic.util.Settings.mumaUserId = it
                            currentServerSetting?.mumaUserId = it
                        }
                        val apiKey = result.api_key ?: result.access_token
                        apiKey?.let {
                            org.moire.ultrasonic.util.Settings.mumaApiKey = it
                            currentServerSetting?.apiKey = it
                            apiKeyEditText?.editText?.setText(it)
                        }
                        // Mirror the web frontend's handleGoogleResponse: a Google-only account
                        // has no known plaintext Subsonic/LMS password on our side, but its
                        // api_key is also accepted as a valid password by /api/auth/login (see
                        // users.py login()), which LMS forwards live for every Subsonic call.
                        // Without this, a Google sign-in would authenticate against
                        // music-manager but leave streaming/library calls unauthenticated.
                        result.user?.username?.let { username ->
                            userNameEditText?.editText?.setText(username)
                            currentServerSetting?.userName = username
                        }
                        apiKey?.let {
                            passwordEditText?.editText?.setText(it)
                            currentServerSetting?.password = it
                        }
                        toast(R.string.muma_sync_logon_success)
                    }
                    "unknown" -> {
                        findNavController().navigate(
                            EditServerFragmentDirections.toGoogleAuth(
                                status = "unknown",
                                displayName = result.google?.display_name,
                                email = result.google?.email,
                                avatarUrl = result.google?.avatar_url,
                                idToken = idToken
                            )
                        )
                    }
                    "request_pending", "request_approved", "request_rejected" -> {
                        findNavController().navigate(
                            EditServerFragmentDirections.toGoogleAuth(
                                status = result.status,
                                displayName = result.request?.display_name,
                                email = result.request?.email,
                                avatarUrl = result.request?.avatar_url,
                                idToken = idToken
                            )
                        )
                    }
                }
            } else {
                toast(R.string.background_task_network_error)
            }
        }
    }
}
