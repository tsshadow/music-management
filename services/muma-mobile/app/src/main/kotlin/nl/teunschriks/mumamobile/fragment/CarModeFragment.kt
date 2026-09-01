/*
 * CarModeFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.graphics.drawable.Drawable
import android.graphics.drawable.LayerDrawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.res.ResourcesCompat
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.StarRating
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.api.subsonic.models.Filter
import nl.teunschriks.mumamobile.api.subsonic.models.Filters
import nl.teunschriks.mumamobile.car.CarModeSession
import nl.teunschriks.mumamobile.car.MixSeed
import nl.teunschriks.mumamobile.car.mixSeedFor
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.home.CardStyle
import nl.teunschriks.mumamobile.home.HomeCard
import nl.teunschriks.mumamobile.home.HomeCardAction
import nl.teunschriks.mumamobile.home.HomeCardAdapter
import nl.teunschriks.mumamobile.home.HomeCardNavigator
import nl.teunschriks.mumamobile.home.HomeCardType
import nl.teunschriks.mumamobile.home.HomeSorts
import nl.teunschriks.mumamobile.home.RecentActivityStore
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.MusicServiceFactory.getMusicService
import nl.teunschriks.mumamobile.service.RxBus
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.setUserRating
import nl.teunschriks.mumamobile.util.themeColor
import nl.teunschriks.mumamobile.util.toTrack
import org.koin.android.ext.android.inject
import org.koin.androidx.scope.ScopeFragment
import timber.log.Timber

/**
 * The driving screen: everything at arm's length, nothing that scrolls.
 *
 * A destination in the navigation graph rather than its own Activity. A second Activity would give
 * a tidier lock-screen story, and would also duplicate the Koin scope, the media session binding
 * and the theme handling -- and a plain Fragment injecting from the wrong scope is a crash that
 * only lands once playback starts, so there is no appetite for a second place to make it.
 */
class CarModeFragment : ScopeFragment() {

    private val mediaPlayerManager: MediaPlayerManager by inject()
    private val store: RecentActivityStore by inject()
    private val session: CarModeSession by inject()
    private val imageLoaderProvider: ImageLoaderProvider by inject()

    private lateinit var adapter: HomeCardAdapter
    private lateinit var hollowStar: Drawable
    private lateinit var fullStar: Drawable

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_car_mode, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        view.findViewById<ImageButton>(R.id.car_mode_close).setOnClickListener {
            session.onDismissed()
            findNavController().popBackStack()
        }

        view.findViewById<ImageButton>(R.id.car_mode_previous)
            .setOnClickListener { mediaPlayerManager.seekToPrevious() }
        view.findViewById<ImageButton>(R.id.car_mode_next)
            .setOnClickListener { mediaPlayerManager.seekToNext() }
        view.findViewById<ImageButton>(R.id.car_mode_play_pause).setOnClickListener {
            mediaPlayerManager.togglePlayPause()
            showNowPlaying(requireView())
        }

        // A FloatingActionButton rather than an ImageButton, so this is typed as the View it is:
        // asking for an ImageButton here compiles and throws the moment the screen opens.
        view.findViewById<View>(R.id.car_mode_microphone).setOnClickListener {
            findNavController().navigate(R.id.mumaVoiceFragment)
        }

        // HomeCardAdapter's click callback returns Unit, so this branches for its side effect
        // rather than producing an action.
        // onClick is named because the adapter's last parameter is onLongClick, so a trailing
        // lambda would silently land there instead.
        adapter = HomeCardAdapter(
            style = CardStyle.GRID,
            onClick = { card ->
                if (card.itemId == MIX_ID) {
                    appendMix()
                } else {
                    when (val action = HomeCardNavigator.actionFor(card)) {
                        is HomeCardAction.Navigate ->
                            findNavController().navigate(action.directions)

                        else -> Unit
                    }
                }
            }
        )

        val tiles: RecyclerView = view.findViewById(R.id.car_mode_tiles)
        tiles.layoutManager = GridLayoutManager(requireContext(), TILE_COLUMNS)
        tiles.adapter = adapter

        setUpStars(view)
        showNowPlaying(view)
        showTiles()
    }

    private fun showNowPlaying(view: View) {
        val track = mediaPlayerManager.currentMediaItem?.toTrack()

        view.findViewById<TextView>(R.id.car_mode_title).text = track?.title.orEmpty()
        view.findViewById<TextView>(R.id.car_mode_artist).text = track?.artist.orEmpty()

        val art: ImageView = view.findViewById(R.id.car_mode_art)
        imageLoaderProvider.executeOn { it.loadImage(art, track, true, 0) }

        view.findViewById<ImageButton>(R.id.car_mode_play_pause).setImageResource(
            if (mediaPlayerManager.isPlaying) R.drawable.media_pause else R.drawable.media_start
        )
    }

    private fun showTiles() {
        val shortcuts = store.recent(Settings.isSetsMode, limit = SHORTCUT_TILES)
        adapter.items = shortcuts + mixCard()
    }

    private fun mixCard() = HomeCard(
        type = HomeCardType.DYNAMIC_PLAYLIST,
        itemId = MIX_ID,
        title = getString(R.string.car_mode_mix)
    )

    /**
     * Five stars, built in code because the only thing that differs between them is which rating
     * they stand for.
     *
     * [STAR_SIZE_DP] is a width budget rather than a taste: five of them plus the screen's own
     * padding have to fit across the narrowest phone this runs on, and 72dp did not.
     *
     * The drawables are the player's own, tinted the same way: they are LayerDrawables whose two
     * layers carry the surface and the accent, and the accent follows the style theme, so the
     * colours have to be applied here rather than named in the layout.
     */
    private fun setUpStars(view: View) {
        hollowStar = ResourcesCompat.getDrawable(resources, R.drawable.star_hollow_outline, null)!!
        fullStar = ResourcesCompat.getDrawable(resources, R.drawable.star_full_outline, null)!!
        tintStar(hollowStar as LayerDrawable)
        tintStar(fullStar as LayerDrawable)

        val row: LinearLayout = view.findViewById(R.id.car_mode_stars)
        row.removeAllViews()

        repeat(STARS) { index ->
            val star = ImageView(requireContext())
            star.layoutParams = LinearLayout.LayoutParams(starSizePx(), starSizePx())
            star.setOnClickListener { rate(index + 1) }
            row.addView(star)
        }

        showStars(mediaPlayerManager.currentMediaItem?.toTrack()?.userRating ?: 0)
    }

    private fun tintStar(drawable: LayerDrawable) {
        drawable.getDrawable(0)
            .setTint(requireContext().themeColor(com.google.android.material.R.attr.colorSurface))
        // The appcompat attribute, not android:colorPrimary: our themes only define the former, so
        // the framework one would not follow the accent setting.
        drawable.getDrawable(1)
            .setTint(requireContext().themeColor(androidx.appcompat.R.attr.colorPrimary))
    }

    private fun starSizePx(): Int = (STAR_SIZE_DP * resources.displayMetrics.density).toInt()

    private fun showStars(rating: Int) {
        val row: LinearLayout = requireView().findViewById(R.id.car_mode_stars)
        repeat(row.childCount) { index ->
            (row.getChildAt(index) as ImageView)
                .setImageDrawable(if (rating > index) fullStar else hollowStar)
        }
    }

    /**
     * 5 means favorite; what the values below it mean stays out of the UI.
     *
     * Written through [setUserRating] rather than onto the Track alone: the item carries a second,
     * frozen copy of the rating in its metadata, and updating only the cached Track lets the
     * rating the item was built with come back (bug report 026).
     */
    private fun rate(stars: Int) {
        val item = mediaPlayerManager.currentMediaItem ?: return
        val trackId = item.toTrack().id

        item.setUserRating(stars)
        RxBus.ratingSubmitter.onNext(RatingUpdate(trackId, StarRating(5, stars.toFloat())))
        showStars(stars)
    }

    /**
     * Appends rather than replaces: the queue is what the last twenty minutes of driving was built
     * from, and throwing it away at a traffic light is not what "Mix" promises.
     */
    private fun appendMix() {
        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val seed = mixSeedFor(mediaPlayerManager.currentMediaItem?.toTrack())
                val tracks = withContext(Dispatchers.IO) {
                    when (seed) {
                        is MixSeed.Genre -> getMusicService().getSongs(
                            filters = Filters().apply { add(Filter(FILTER_GENRE, seed.name)) },
                            ratingMin = null,
                            ratingMax = null,
                            count = MIX_SIZE,
                            offset = 0,
                            sortMethod = HomeSorts.ADDED
                        ).getTracks()

                        MixSeed.Favorites -> getMusicService().getSongs(
                            filters = Filters(),
                            ratingMin = FAVORITE_RATING_MIN,
                            ratingMax = null,
                            count = MIX_SIZE,
                            offset = 0,
                            sortMethod = HomeSorts.ADDED
                        ).getTracks()
                    }
                }

                mediaPlayerManager.addToPlaylist(
                    tracks.shuffled(),
                    autoPlay = false,
                    shuffle = false,
                    insertionMode = MediaPlayerManager.InsertionMode.APPEND
                )
            } catch (e: Exception) {
                Timber.w(e, "Mix could not be built")
            }
        }
    }

    private companion object {
        const val MIX_ID = "car-mode-mix"
        const val MIX_SIZE = 50
        const val SHORTCUT_TILES = 3
        const val TILE_COLUMNS = 2
        const val STARS = 5
        const val STAR_SIZE_DP = 56
        const val FAVORITE_RATING_MIN = 4
        const val FILTER_GENRE = "GENRE"
    }
}
