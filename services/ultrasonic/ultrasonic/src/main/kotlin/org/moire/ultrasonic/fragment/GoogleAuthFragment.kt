package org.moire.ultrasonic.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import com.squareup.picasso.Picasso
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.koin.android.ext.android.inject
import org.moire.ultrasonic.R
import org.moire.ultrasonic.api.subsonic.SubsonicAPIClient
import org.moire.ultrasonic.databinding.GoogleAuthFragmentBinding
import org.moire.ultrasonic.util.SecureSettings
import timber.log.Timber

class GoogleAuthFragment : Fragment() {

    private val navArgs by navArgs<GoogleAuthFragmentArgs>()
    private val subsonicAPIClient: SubsonicAPIClient by inject()
    private var _binding: GoogleAuthFragmentBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = GoogleAuthFragmentBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setupUI()
    }

    private fun setupUI() {
        val status = navArgs.status
        val displayName = navArgs.displayName
        val email = navArgs.email
        val avatarUrl = navArgs.avatarUrl
        val idToken = navArgs.idToken

        if (!avatarUrl.isNullOrEmpty()) {
            Picasso.get().load(avatarUrl).placeholder(R.drawable.chat_user_avatar).into(binding.googleAvatar)
        }

        when (status) {
            "unknown" -> {
                binding.authTitle.setText(R.string.request_access_title)
                binding.authMessage.text = getString(R.string.request_access_message, displayName, email)
                binding.authActionButton.setText(R.string.request_access_button)
                binding.authActionButton.setOnClickListener {
                    if (idToken != null) {
                        performAccessRequest(idToken)
                    }
                }
            }
            "request_pending" -> {
                binding.authTitle.setText(R.string.pending_review_title)
                binding.authMessage.setText(R.string.pending_review_message)
                binding.authActionButton.visibility = View.GONE
            }
            "request_rejected" -> {
                binding.authTitle.setText(R.string.rejected_title)
                binding.authMessage.setText(R.string.rejected_message)
                binding.authActionButton.visibility = View.GONE
            }
            "request_approved" -> {
                binding.authTitle.setText(R.string.common_ok)
                binding.authMessage.setText(R.string.approved_retry_message)
                binding.authActionButton.setText(R.string.try_again_button)
                binding.authActionButton.setOnClickListener {
                    findNavController().popBackStack()
                }
            }
        }
    }

    private fun performAccessRequest(idToken: String) {
        binding.authActionButton.isEnabled = false
        binding.authProgress.visibility = View.VISIBLE

        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val mumaApi = subsonicAPIClient.mumaApi?.api
                    val response = mumaApi?.accessRequest(org.moire.ultrasonic.api.muma.GoogleAuthRequest(idToken))?.execute()
                    if (response?.isSuccessful == true) {
                        response.body()
                    } else {
                        null
                    }
                } catch (e: Exception) {
                    Timber.e(e, "Failed to perform access request")
                    null
                }
            }

            binding.authProgress.visibility = View.GONE
            if (result != null && result.status == "ok") {
                // Move to pending state
                findNavController().navigate(
                    GoogleAuthFragmentDirections.toGoogleAuth(
                        status = "request_pending",
                        displayName = navArgs.displayName,
                        email = navArgs.email,
                        avatarUrl = navArgs.avatarUrl,
                        idToken = idToken
                    )
                )
            } else {
                binding.authActionButton.isEnabled = true
                // Show error
                org.moire.ultrasonic.util.Util.toast(R.string.background_task.network_error)
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
