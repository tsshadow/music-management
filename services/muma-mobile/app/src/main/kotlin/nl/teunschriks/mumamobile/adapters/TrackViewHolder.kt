package nl.teunschriks.mumamobile.adapters

import android.util.TypedValue
import android.view.View
import android.widget.Checkable
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.view.isGone
import androidx.core.view.isVisible
import androidx.lifecycle.MutableLiveData
import androidx.media3.common.StarRating
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.progressindicator.CircularProgressIndicator
import io.reactivex.rxjava3.disposables.CompositeDisposable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.DownloadService
import nl.teunschriks.mumamobile.service.DownloadState
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.service.plusAssign
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.TrackDateFormatter
import nl.teunschriks.mumamobile.util.Util
import nl.teunschriks.mumamobile.util.themeColor
import org.koin.core.component.KoinComponent

const val INDICATOR_THICKNESS_INDEFINITE = 5
const val INDICATOR_THICKNESS_DEFINITE = 10

/**
 * Used to display songs and videos in a `ListView`.
 */
class TrackViewHolder(val view: View) :
    RecyclerView.ViewHolder(view),
    Checkable,
    KoinComponent,
    CoroutineScope by CoroutineScope(Dispatchers.IO) {

    companion object {
        /** `bg-brand/20` in the web UI: the brand colour at 20% alpha over the row. */
        private const val SELECTION_TINT_ALPHA = 0x33000000
        private const val SELECTION_TINT_MASK = 0x00FFFFFF
    }

    var entry: Track? = null
        private set
    var songLayout: LinearLayout = view.findViewById(R.id.song_layout)
    var drag: ImageView = view.findViewById(R.id.song_drag)
    var observableChecked = MutableLiveData(false)

    private var isCheckedInternal = false

    private var rating: LinearLayout = view.findViewById(R.id.song_rating)
    private var fiveStar1: ImageView = view.findViewById(R.id.song_five_star_1)
    private var fiveStar2: ImageView = view.findViewById(R.id.song_five_star_2)
    private var fiveStar3: ImageView = view.findViewById(R.id.song_five_star_3)
    private var fiveStar4: ImageView = view.findViewById(R.id.song_five_star_4)
    private var fiveStar5: ImageView = view.findViewById(R.id.song_five_star_5)
    private var track: TextView = view.findViewById(R.id.song_track_number)
    private var album: TextView = view.findViewById(R.id.song_album)
    private var title: TextView = view.findViewById(R.id.song_title)
    private var artist: TextView = view.findViewById(R.id.song_artist)
    private var date: TextView = view.findViewById(R.id.song_date)
    private var duration: TextView = view.findViewById(R.id.song_duration)
    private var statusImage: ImageView = view.findViewById(R.id.song_status_image)
    private var progressIndicator: CircularProgressIndicator =
        view.findViewById(R.id.song_status_progress)

    init {
        progressIndicator.max = 100
    }

    private var isMaximized = false
    private var cachedStatus = DownloadState.UNKNOWN
    private var isPlayingCached = false

    private var rxBusSubscription: CompositeDisposable? = null

    @Suppress("ComplexMethod")
    fun setSong(song: Track, checkable: Boolean, draggable: Boolean, isSelected: Boolean = false) {
        entry = song

        val entryDescription = Util.readableEntryDescription(song)

        artist.text = song.artist ?: ""
        title.text = entryDescription.title
        duration.text = entryDescription.duration
        album.text = song.album ?: ""
        album.isVisible = true

        val dateText = if (Settings.trackListLines >= Settings.TRACK_LIST_LINES_DETAILED) {
            TrackDateFormatter.format(song.date, song.year)
        } else {
            // The compact row has never had space for more than the year.
            song.year?.takeIf { it > 0 }?.toString()
        }

        if (dateText != null) {
            date.text = dateText
            date.isVisible = true
        } else {
            date.isVisible = false
        }

        if (Settings.shouldShowTrackNumber && song.track != null && song.track!! > 0) {
            track.text = entryDescription.trackNumber
        } else {
            if (!track.isGone) track.isGone = true
        }

        val checkValue = (checkable && !song.isVideo)
        if (checkValue) initChecked(isSelected) else initChecked(false)
        if (drag.isVisible != draggable) drag.isVisible = draggable

        if (ActiveServerProvider.isOffline()) {
            rating.isGone = true
        } else {
            setupStarButtons()
        }

        // Instead of blocking the UI thread while looking up the current state,
        // launch the request in an IO thread and propagate the result through RX
        launch {
            val state = DownloadService.getDownloadState(song)
            RxBus.trackDownloadStatePublisher.onNext(
                RxBus.TrackDownloadState(song.id, state, null)
            )
        }

        updateFiveStars(entry?.userRating ?: 0)

        if (song.isVideo) {
            artist.isGone = true
            progressIndicator.isGone = true
        }

        // Create new Disposable for the new Subscriptions
        rxBusSubscription = CompositeDisposable()
        rxBusSubscription!! += RxBus.playerStateObservable.subscribe {
            setPlayIcon(it.track?.id == song.id && it.index == bindingAdapterPosition)
        }

        rxBusSubscription!! += RxBus.trackDownloadStateObservable.subscribe {
            if (it.id != song.id) return@subscribe
            updateStatus(it.state, it.progress)
        }

        // Listen for rating updates
        rxBusSubscription!! += RxBus.ratingPublishedObservable.subscribe {
            launch(Dispatchers.Main) {
                // Ignore updates which are not for the current song
                if (it.id != song.id) return@launch

                if (it.rating is StarRating) {
                    updateFiveStars(it.rating.starRating.toInt())
                }
            }
        }
    }

    // This is called when the Holder is recycled and receives a new Song
    fun dispose() {
        rxBusSubscription?.dispose()
    }

    private val playingIcon by lazy {
        ContextCompat.getDrawable(view.context, R.drawable.ic_stat_play)!!
    }

    /** The row's title. Exposed so a test can read the mark a playing row carries. */
    internal val titleView: TextView get() = title

    @Suppress("MagicNumber")
    internal fun setPlayIcon(isPlaying: Boolean) {
        if (isPlaying && !isPlayingCached) {
            isPlayingCached = true
            title.setCompoundDrawablesWithIntrinsicBounds(
                playingIcon,
                null,
                null,
                null
            )
            title.setTextColor(brandColor())
        } else if (!isPlaying && isPlayingCached) {
            isPlayingCached = false
            title.setCompoundDrawablesWithIntrinsicBounds(
                0,
                0,
                0,
                0
            )
            title.setTextColor(view.context.themeColor(android.R.attr.textColorPrimary))
        }
    }

    private fun setupStarButtons() {
        rating.isVisible = true

        // Five star rating has no click handler because in the
        // track view theres not enough space
    }

    @Suppress("MagicNumber")
    private fun updateFiveStars(rating: Int) {
        fiveStar1.setImageResource(
            if (rating > 0) R.drawable.ic_star_full else R.drawable.ic_star_hollow
        )
        fiveStar2.setImageResource(
            if (rating > 1) R.drawable.ic_star_full else R.drawable.ic_star_hollow
        )
        fiveStar3.setImageResource(
            if (rating > 2) R.drawable.ic_star_full else R.drawable.ic_star_hollow
        )
        fiveStar4.setImageResource(
            if (rating > 3) R.drawable.ic_star_full else R.drawable.ic_star_hollow
        )
        fiveStar5.setImageResource(
            if (rating > 4) R.drawable.ic_star_full else R.drawable.ic_star_hollow
        )
    }

    private fun updateStatus(status: DownloadState, progress: Int?) {
        progressIndicator.progress = progress ?: 0

        if (status == cachedStatus) return
        cachedStatus = status

        when (status) {
            DownloadState.DONE -> {
                showStatusImage(R.drawable.ic_downloaded)
            }
            DownloadState.PINNED -> {
                showStatusImage(R.drawable.ic_menu_pin)
            }
            DownloadState.FAILED -> {
                showStatusImage(R.drawable.ic_baseline_error)
            }
            DownloadState.DOWNLOADING -> {
                showProgress()
            }
            DownloadState.RETRYING,
            DownloadState.QUEUED
            -> {
                showIndefiniteProgress()
            }
            else -> {
                // This handles CANCELLED too.
                // Usually it means no error, just that the track wasn't downloaded
                showStatusImage(null)
            }
        }
    }

    private fun showStatusImage(image: Int?) {
        progressIndicator.isGone = true
        statusImage.isVisible = true
        if (image != null) {
            statusImage.setImageResource(image)
        } else {
            statusImage.setImageDrawable(null)
        }
    }

    private fun showIndefiniteProgress() {
        statusImage.isGone = true
        progressIndicator.isVisible = true
        progressIndicator.isIndeterminate = true
        progressIndicator.indicatorDirection =
            CircularProgressIndicator.INDICATOR_DIRECTION_COUNTERCLOCKWISE
        progressIndicator.trackThickness = INDICATOR_THICKNESS_INDEFINITE
    }

    private fun showProgress() {
        statusImage.isGone = true
        progressIndicator.isVisible = true
        progressIndicator.isIndeterminate = false
        progressIndicator.indicatorDirection =
            CircularProgressIndicator.INDICATOR_DIRECTION_CLOCKWISE
        progressIndicator.trackThickness = INDICATOR_THICKNESS_DEFINITE
    }

    /**
     * The brand colour the rest of the app marks the current mode with: green for songs, blue for
     * sets. Read per call rather than cached, because a holder outlives a mode switch.
     */
    private fun brandColor(): Int = if (Settings.isSetsMode) {
        view.context.themeColor(R.attr.brandColorSets)
    } else {
        view.context.themeColor(androidx.appcompat.R.attr.colorPrimary)
    }

    /**
     * Selection tints the row; playing marks the title (see [setPlayIcon]). They used to be the
     * same card, so a row could not say it was both -- and the card was named by resource id,
     * which overrode the background the active style had put on the row in the layout.
     */
    private fun updateBackground() {
        if (isCheckedInternal) {
            songLayout.setBackgroundColor(brandColor() and SELECTION_TINT_MASK or SELECTION_TINT_ALPHA)
        } else {
            val background = TypedValue()
            view.context.theme.resolveAttribute(R.attr.listRowBackground, background, true)
            if (background.resourceId == 0) {
                songLayout.background = null
            } else {
                songLayout.setBackgroundResource(background.resourceId)
            }
        }
    }

    /*
     * Set the checked value and re-init the MutableLiveData.
     * If we would post a new value, there might be a short glitch where the track is shown with its
     * old selection status before the posted value has been processed.
     */
    private fun initChecked(newStatus: Boolean) {
        observableChecked = MutableLiveData(newStatus)
        isCheckedInternal = newStatus
        updateBackground()
    }

    /*
     * To be correct, this method doesn't directly set the checked status.
     * It only notifies the observable. If the selection tracker accepts the selection
     *  (might be false for Singular SelectionTrackers) then it will cause the actual modification.
     */
    override fun setChecked(newStatus: Boolean) {
        isCheckedInternal = newStatus
        observableChecked.postValue(newStatus)
        updateBackground()
    }

    override fun isChecked(): Boolean = isCheckedInternal

    override fun toggle() {
        setChecked(!isCheckedInternal)
    }

    fun maximizeOrMinimize() {
        isMaximized = !isMaximized

        title.isSingleLine = !isMaximized
        artist.isSingleLine = !isMaximized
    }
}
