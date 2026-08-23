/*
 * MumaVoiceFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.Manifest
import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts.RequestPermission
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
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
import nl.teunschriks.mumamobile.voice.VoiceExplanation
import nl.teunschriks.mumamobile.voice.VoiceQuery
import nl.teunschriks.mumamobile.voice.VoiceRequest
import nl.teunschriks.mumamobile.voice.VoiceTraceLog
import org.koin.android.ext.android.inject
import org.koin.androidx.scope.ScopeFragment
import timber.log.Timber

/**
 * @brief MuMa's own voice entry point.
 *
 * @details Microphone, speech to text, string, and from there the same parser, resolver and query
 * engine Android Auto uses. The speech layer knows nothing about genres; this screen does nothing
 * to the words beyond handing them on.
 *
 * It listens the moment it opens rather than waiting to be tapped. Everything that reaches this
 * screen -- the car's microphone button, the quick settings tile, the menu -- is already a decision
 * to say something, so a second tap was a tap spent proving it twice, at the one moment a pair of
 * hands is busiest. The microphone below is therefore a repeat button, not a start button.
 *
 * Where the car has to guess, this can ask. An ambiguous reading puts the question on screen as
 * chips and reopens the microphone at the same time, so "het label" can be spoken or tapped. Either
 * answer pins the kind and runs the *same* resolver again rather than taking a shortcut around it.
 *
 * The text field underneath is the same pipeline without the microphone, which is what makes a
 * phrasing testable at a desk instead of on a motorway. Below that is what the request became, in
 * words: [VoiceExplanation] exists because the object a request resolves to prints itself as the
 * server's JSON, and that is unreadable at exactly the moment it matters.
 *
 * A `ScopeFragment` rather than a plain one, because [MediaPlayerManager] is scoped to the hosting
 * `NavigationActivity` and a plain fragment injects from the root scope, where it is not. The
 * injection is lazy, so getting that wrong costs nothing until the moment something resolves and
 * this screen actually has music to start.
 */
class MumaVoiceFragment : ScopeFragment() {

    private val mediaPlayerManager: MediaPlayerManager by inject()

    private var status: TextView? = null
    private var heard: TextView? = null
    private var choices: ChipGroup? = null
    private var capture: SpeechCapture? = null

    private var explanation: LinearLayout? = null
    private var rawToggle: TextView? = null
    private var rawScroll: View? = null
    private var raw: TextView? = null

    /** Posts the return to whatever opened this screen, and is cancelled by any sign of life. */
    private val clock = Handler(Looper.getMainLooper())
    private var leaving: Runnable? = null

    /**
     * The names the recogniser is biased towards, loaded once when the screen opens.
     *
     * Held rather than fetched at the microphone tap, because the lookup is a server call and the
     * tap is on the main thread. An empty list is not a failure: the microphone still works and
     * simply goes unbiased, which is what it did before.
     */
    private var biasing: List<String> = emptyList()

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

    @SuppressLint("ClickableViewAccessibility")
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, getString(R.string.muma_voice_title))

        status = view.findViewById(R.id.muma_voice_status)
        heard = view.findViewById(R.id.muma_voice_heard)
        choices = view.findViewById(R.id.muma_voice_choices)
        explanation = view.findViewById(R.id.muma_voice_explanation)
        rawToggle = view.findViewById(R.id.muma_voice_raw_toggle)
        rawScroll = view.findViewById(R.id.muma_voice_raw_scroll)
        raw = view.findViewById(R.id.muma_voice_raw)
        capture = SpeechCapture(requireContext())

        // Touching the screen at all means somebody is reading it, and a screen that walks out from
        // under a reader is worse than one that stays too long. Returning false so the touch still
        // reaches whatever it was aimed at.
        view.setOnTouchListener { _, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) stay()
            false
        }

        view.findViewById<View>(R.id.muma_voice_mic)?.setOnClickListener {
            stay()
            onMicrophoneTapped()
        }

        rawToggle?.setOnClickListener {
            stay()
            showRaw(rawScroll?.isVisible != true)
        }

        val input = view.findViewById<EditText>(R.id.muma_voice_input)
        input?.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                val typed = input.text.toString().trim()
                if (typed.isNotEmpty()) {
                    stay()
                    input.text.clear()
                    run(listOf(typed), VoiceEntryPoint.TEXT_INPUT)
                }
                true
            } else {
                false
            }
        }

        lifecycleScope.launch {
            biasing = withContext(Dispatchers.IO) {
                runCatching {
                    MusicServiceVocabulary(MusicServiceFactory.getMusicService()).prominentGenres()
                }.getOrElse {
                    Timber.w(it, "could not load the genres to bias speech towards")
                    emptyList()
                }
            }
        }

        // Only on a genuinely new screen. A rotation recreates the view with a resolution already
        // on it, and starting to listen over the top of that would throw the answer away.
        if (savedInstanceState == null) listenOnOpening()
    }

    override fun onPause() {
        capture?.stop()
        stay()
        super.onPause()
    }

    override fun onDestroyView() {
        stay()
        explanation = null
        rawToggle = null
        rawScroll = null
        raw = null
        super.onDestroyView()
    }

    /**
     * Opens the microphone by itself, but never the permission dialog.
     *
     * Being asked for a permission by a screen that has not been looked at yet is how a request
     * gets denied for good, and this screen still works without the microphone -- the text field
     * below runs the same pipeline. So the first time round, the button does the asking.
     */
    private fun listenOnOpening() {
        val granted = ContextCompat.checkSelfPermission(
            requireContext(),
            Manifest.permission.RECORD_AUDIO
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

        if (granted) listen()
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
            },
            biasing = biasing
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

        lifecycleScope.launch {
            val resolution = VoiceRequest.resolveSpoken(readings, entryPoint, heardWith)
            act(resolution, readings.firstOrNull().orEmpty())
        }
    }

    private fun act(resolution: QueryResolution, spoken: String) {
        explain(resolution)

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
                        setOnClickListener {
                            stay()
                            answer(candidate)
                        }
                    }
                )
            }
            visibility = View.VISIBLE
        }

        if (capture?.isAvailable() == true) listenForAnswer()
    }

    /** Unbiased on purpose: this is listening for a kind, not for a name. */
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

            addRow(
                R.string.voice_explain_result,
                getString(R.string.voice_explain_result_tracks, tracks.size)
            )

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
            leaveInAMoment()
        }
    }

    /**
     * Goes back to whatever opened this screen, unless somebody is still reading it.
     *
     * The music is already playing by the time this is posted, so the screen has said everything it
     * has to say; leaving it up means the next glance at the phone is at a dead end rather than at
     * the driving screen. Any touch cancels it for good -- see [stay].
     */
    private fun leaveInAMoment() {
        stay()
        val run = Runnable {
            leaving = null
            if (isResumed) findNavController().popBackStack()
        }
        leaving = run
        clock.postDelayed(run, RETURN_DELAY_MS)
    }

    /** Cancels a pending return. Safe to call when there is none, which is most of the time. */
    private fun stay() {
        leaving?.let { clock.removeCallbacks(it) }
        leaving = null
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

    /**
     * What is playing, as a sentence.
     *
     * This used to be `target.filters.toString()`, which is the JSON the server is sent:
     * `Playing [{"name":"GENRE","value":"hardstyle"}]`. Only the naming rows are used, because the
     * order and the length belong in the diagnosis below rather than in a sentence.
     */
    private fun describe(target: Target): String {
        val named = VoiceExplanation.names(VoiceExplanation.of(target))
        if (named.isEmpty()) return getString(R.string.muma_voice_selection)
        return named.joinToString(", ") { "${getString(labelOf(it.field))} ${valueOf(it)}" }
    }

    /** Replaces the diagnosis with this request's, raw trace collapsed again. */
    private fun explain(resolution: QueryResolution) {
        val panel = explanation ?: return
        panel.removeAllViews()
        VoiceExplanation.of(resolution).forEach { addRow(labelOf(it.field), valueOf(it)) }

        raw?.text = resolution.trace.render()
        rawToggle?.isVisible = true
        showRaw(false)
    }

    private fun addRow(label: Int, value: String) {
        val panel = explanation ?: return
        val row = layoutInflater.inflate(R.layout.voice_explanation_row, panel, false)
        row.findViewById<TextView>(R.id.voice_explanation_label).setText(label)
        row.findViewById<TextView>(R.id.voice_explanation_value).text = value
        panel.addView(row)
    }

    private fun showRaw(visible: Boolean) {
        rawScroll?.isVisible = visible
        rawToggle?.setText(
            if (visible) R.string.voice_explain_raw_hide else R.string.voice_explain_raw_show
        )
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

    private fun labelOf(field: VoiceExplanation.Field): Int = when (field) {
        VoiceExplanation.Field.HEARD -> R.string.voice_explain_heard
        VoiceExplanation.Field.GENRE -> R.string.voice_explain_genre
        VoiceExplanation.Field.LABEL -> R.string.voice_explain_label
        VoiceExplanation.Field.ARTIST -> R.string.voice_explain_artist
        VoiceExplanation.Field.ALBUM -> R.string.voice_explain_album
        VoiceExplanation.Field.PLAYLIST -> R.string.voice_explain_playlist
        VoiceExplanation.Field.YEAR -> R.string.voice_explain_year
        VoiceExplanation.Field.RATING -> R.string.voice_explain_rating
        VoiceExplanation.Field.SETS -> R.string.voice_explain_sets
        VoiceExplanation.Field.ORDER -> R.string.voice_explain_order
        VoiceExplanation.Field.QUESTION -> R.string.voice_explain_question
        VoiceExplanation.Field.REASON -> R.string.voice_explain_reason
    }

    /**
     * A row's value in this device's language.
     *
     * Only two fields need translating: everything else is a name the library spells, and a genre
     * called "Uptempo Hardcore" is called that in every language the app has.
     */
    private fun valueOf(row: VoiceExplanation.Row): String = when (row.field) {
        VoiceExplanation.Field.SETS -> getString(R.string.voice_explain_sets_value)
        VoiceExplanation.Field.ORDER -> getString(
            when (row.value) {
                VoiceExplanation.Order.ADDED -> R.string.voice_explain_order_added
                VoiceExplanation.Order.RANDOM -> R.string.voice_explain_order_random
                else -> R.string.voice_explain_order_released
            }
        )

        else -> row.value
    }

    private fun resolver() =
        QueryResolver(MusicServiceVocabulary(MusicServiceFactory.getMusicService()))

    private companion object {
        /** Long enough to read the diagnosis at a traffic light, short enough not to be a wall. */
        const val RETURN_DELAY_MS = 10_000L
    }
}
