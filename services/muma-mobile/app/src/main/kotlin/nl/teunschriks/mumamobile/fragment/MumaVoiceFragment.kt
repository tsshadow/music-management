/*
 * MumaVoiceFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.Manifest
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.MusicServiceFactory
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util.applyTheme
import nl.teunschriks.mumamobile.voice.Candidate
import nl.teunschriks.mumamobile.voice.DisambiguationWords
import nl.teunschriks.mumamobile.voice.EntityKind
import nl.teunschriks.mumamobile.voice.MusicServiceVocabulary
import nl.teunschriks.mumamobile.voice.ParsedQuery
import nl.teunschriks.mumamobile.voice.QueryResolution
import nl.teunschriks.mumamobile.voice.QueryResolver
import nl.teunschriks.mumamobile.voice.QueryTrace
import nl.teunschriks.mumamobile.voice.SpeechCapture
import nl.teunschriks.mumamobile.voice.Target
import nl.teunschriks.mumamobile.voice.VoiceEntryPoint
import nl.teunschriks.mumamobile.voice.VoiceQuery
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import org.koin.android.ext.android.inject
import timber.log.Timber

/**
 * @brief MuMa's own voice entry point.
 *
 * @details Microphone, speech to text, string, and from there the same parser, resolver and query
 * engine Android Auto uses. The speech layer knows nothing about genres; this screen does nothing
 * to the words beyond handing them on.
 *
 * Where the car has to guess, this can ask. An ambiguous reading puts the question on screen as
 * chips and reopens the microphone at the same time, so "het label" can be spoken or tapped. Either
 * answer pins the kind and runs the *same* resolver again rather than taking a shortcut around it.
 *
 * The text field underneath is the same pipeline without the microphone, which is what makes a
 * phrasing testable at a desk instead of on a motorway.
 */
class MumaVoiceFragment : Fragment() {

    private val mediaPlayerManager: MediaPlayerManager by inject()

    private var status: TextView? = null
    private var heard: TextView? = null
    private var choices: ChipGroup? = null
    private var capture: SpeechCapture? = null

    /** The question currently on screen, so a spoken answer knows what it is answering. */
    private var question: QueryResolution.Ambiguous? = null
    private var questionQuery: String? = null

    private val askForMicrophone = registerForActivityResult(RequestPermission()) { granted ->
        if (granted) listen() else status?.setText(R.string.muma_voice_needs_microphone)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme(this.context)
        super.onCreate(savedInstanceState)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.muma_voice, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, getString(R.string.muma_voice_title))

        status = view.findViewById(R.id.muma_voice_status)
        heard = view.findViewById(R.id.muma_voice_heard)
        choices = view.findViewById(R.id.muma_voice_choices)
        capture = SpeechCapture(requireContext())

        view.findViewById<MaterialButton>(R.id.muma_voice_mic)?.setOnClickListener {
            onMicrophoneTapped()
        }

        val input = view.findViewById<EditText>(R.id.muma_voice_input)
        input?.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                val typed = input.text.toString().trim()
                if (typed.isNotEmpty()) {
                    input.text.clear()
                    run(listOf(typed), VoiceEntryPoint.TEXT_INPUT)
                }
                true
            } else {
                false
            }
        }
    }

    override fun onPause() {
        capture?.stop()
        super.onPause()
    }

    private fun onMicrophoneTapped() {
        val granted = ContextCompat.checkSelfPermission(
            requireContext(),
            Manifest.permission.RECORD_AUDIO
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

        if (granted) listen() else askForMicrophone.launch(Manifest.permission.RECORD_AUDIO)
    }

    private fun listen() {
        if (capture?.isAvailable() != true) {
            status?.setText(R.string.muma_voice_no_recogniser)
            return
        }

        status?.setText(R.string.muma_voice_listening)
        heard?.text = ""
        capture?.start(
            onPartial = { heard?.text = it },
            onResult = { readings ->
                heard?.text = readings.firstOrNull()?.text.orEmpty()
                onHeard(readings)
            },
            onError = {
                status?.setText(R.string.muma_voice_prompt)
            }
        )
    }

    /** A spoken answer to a question that is on screen never goes through the full parser. */
    private fun onHeard(readings: List<SpeechCapture.Hypothesis>) {
        val standing = question
        if (standing != null) {
            val offered = standing.candidates.map { it.kind }
            val answered = readings.firstNotNullOfOrNull {
                DisambiguationWords.kindOf(it.text, offered)
            }
            if (answered != null) {
                answer(standing.candidates.first { it.kind == answered })
                return
            }
        }

        run(readings.map { it.text }, VoiceEntryPoint.MUMA_VOICE, readings)
    }

    private fun run(
        readings: List<String>,
        entryPoint: String,
        heardWith: List<SpeechCapture.Hypothesis> = emptyList()
    ) {
        clearQuestion()
        status?.setText(R.string.muma_voice_working)

        val trace = QueryTrace(entryPoint, "app")
        heardWith.forEach { trace.hypothesis(it.text, it.confidence) }

        lifecycleScope.launch {
            val resolution = withContext(Dispatchers.IO) {
                runCatching { resolver().resolveFirst(readings, trace) }.getOrElse {
                    Timber.w(it, "voice query failed")
                    trace.outcome("failed: ${it.javaClass.simpleName}")
                    QueryResolution.NoMatch(it.javaClass.simpleName, trace)
                }
            }
            VoiceTraceLog.record(trace)
            act(resolution, readings.firstOrNull().orEmpty())
        }
    }

    private fun act(resolution: QueryResolution, spoken: String) {
        when (resolution) {
            is QueryResolution.Resolved -> play(resolution.target)
            is QueryResolution.NoMatch ->
                status?.text = getString(R.string.muma_voice_no_match, spoken)
            is QueryResolution.Ambiguous -> ask(resolution, spoken)
        }
    }

    /**
     * Puts the question, and listens again at once.
     *
     * The chips are the reliable half and the microphone the convenient one; neither is the only
     * way to answer, because a car park is a bad place to have to look at a screen and a quiet room
     * is a bad place to have to talk.
     */
    private fun ask(ambiguous: QueryResolution.Ambiguous, spoken: String) {
        question = ambiguous
        questionQuery = spoken
        status?.text = getString(R.string.muma_voice_ask, ambiguous.term)

        choices?.apply {
            removeAllViews()
            ambiguous.candidates.forEach { candidate ->
                addView(
                    Chip(requireContext()).apply {
                        text = getString(labelOf(candidate.kind))
                        isClickable = true
                        setOnClickListener { answer(candidate) }
                    }
                )
            }
            visibility = View.VISIBLE
        }

        if (capture?.isAvailable() == true) listenForAnswer()
    }

    private fun listenForAnswer() = capture?.start(
        onPartial = { heard?.text = it },
        onResult = { onHeard(it) },
        onError = { /* the chips are still on screen */ }
    )

    /** Pins the chosen kind and runs the same resolver again, rather than around it. */
    private fun answer(candidate: Candidate) {
        val spoken = questionQuery.orEmpty()
        val term = question?.term.orEmpty()
        clearQuestion()
        status?.setText(R.string.muma_voice_working)

        val trace = QueryTrace(VoiceEntryPoint.MUMA_VOICE, "app")
        trace.note("the kind was answered: ${candidate.kind}")

        lifecycleScope.launch {
            val resolution = withContext(Dispatchers.IO) {
                val parsed = VoiceQuery.parse(spoken, trace) ?: ParsedQuery()
                resolver().resolve(parsed, null, trace, candidate.kind)
            }
            VoiceTraceLog.record(trace)
            act(resolution, term)
        }
    }

    private fun play(target: Target) {
        lifecycleScope.launch {
            val tracks = withContext(Dispatchers.IO) {
                runCatching { tracksFor(target) }.getOrElse {
                    Timber.w(it, "could not fetch the tracks a voice query resolved to")
                    emptyList()
                }
            }

            if (tracks.isEmpty()) {
                status?.text = getString(R.string.muma_voice_no_match, describe(target))
                return@launch
            }

            mediaPlayerManager.addToPlaylist(
                songs = tracks,
                autoPlay = true,
                shuffle = false,
                insertionMode = MediaPlayerManager.InsertionMode.CLEAR
            )
            status?.text = getString(R.string.muma_voice_playing, describe(target))
        }
    }

    private fun tracksFor(target: Target): List<Track> {
        val service = MusicServiceFactory.getMusicService()
        return when (target) {
            is Target.Filtered -> service.getSongs(
                filters = target.filters,
                ratingMin = target.ratingMin,
                ratingMax = target.ratingMax,
                count = Settings.maxSongs,
                offset = 0,
                sortMethod = target.sortMethod
            ).getTracks()

            is Target.Item -> when (target.kind) {
                EntityKind.PLAYLIST -> service.getPlaylist(target.id, target.name).getTracks()
                else -> service.getAlbumAsDir(target.id, target.name, false).getTracks()
            }
        }
    }

    private fun describe(target: Target): String = when (target) {
        is Target.Item -> target.name
        is Target.Filtered -> target.filters.toString()
    }

    private fun clearQuestion() {
        question = null
        questionQuery = null
        choices?.apply {
            removeAllViews()
            visibility = View.GONE
        }
    }

    private fun labelOf(kind: EntityKind): Int = when (kind) {
        EntityKind.GENRE -> R.string.muma_voice_kind_genre
        EntityKind.LABEL -> R.string.muma_voice_kind_label
        EntityKind.ARTIST -> R.string.muma_voice_kind_artist
        EntityKind.ALBUM -> R.string.muma_voice_kind_album
        EntityKind.PLAYLIST -> R.string.muma_voice_kind_playlist
    }

    private fun resolver() =
        QueryResolver(MusicServiceVocabulary(MusicServiceFactory.getMusicService()))
}
