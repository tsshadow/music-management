/*
 * TrackInfoModalFragment.kt
 * Copyright (C) 2009-2025 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment.muma

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.Toast
import androidx.core.os.BundleCompat
import androidx.core.os.bundleOf
import androidx.core.view.isVisible
import androidx.fragment.app.setFragmentResult
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import com.google.android.material.chip.Chip
import java.util.Locale
import org.koin.android.ext.android.inject
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.isOffline
import nl.teunschriks.mumamobile.data.ActiveServerProvider.Companion.shouldUseId3Tags
import nl.teunschriks.mumamobile.databinding.mumaTrackInfoBinding
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.subsonic.ImageLoaderProvider
import nl.teunschriks.mumamobile.util.Settings
import nl.teunschriks.mumamobile.util.Util

/**
 * Everything we know about a single track, as a bottom sheet.
 *
 * The sheet only renders and reports: the artist and album rows, the action buttons and the
 * rating all hand back to whoever opened it (see [RESULT_KEY]), so the navigation, sharing and
 * bookmarking logic stays in one place in PlayerFragment instead of being duplicated here.
 */
class TrackInfoModalFragment : BottomSheetDialogFragment() {

    private var _binding: mumaTrackInfoBinding? = null
    private val binding get() = _binding!!

    private val imageLoaderProvider: ImageLoaderProvider by inject()

    private lateinit var track: Track

    /** Kept locally so the stars respond instantly; the real update is the caller's job. */
    private var rating: Int = 0

    companion object {
        const val TAG = "TrackInfoModal"

        /** Fragment result key. The bundle always carries [RESULT_TRACK]. */
        const val RESULT_KEY = "trackInfoResult"

        /** The track the sheet was opened for, so the caller need not remember it. */
        const val RESULT_TRACK = "track"

        /** Menu item id of the action that was picked, or absent for a rating change. */
        const val RESULT_ACTION_ID = "actionId"

        /** New star rating, or absent when an action was picked. */
        const val RESULT_RATING = "rating"

        private const val ARG_TRACK = "track"
        private const val BLUR_RADIUS = 32f

        fun newInstance(track: Track) = TrackInfoModalFragment().apply {
            arguments = bundleOf(ARG_TRACK to track)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setStyle(STYLE_NORMAL, R.style.Ultrasonic_TrackInfoSheetTheme)
        track = BundleCompat.getSerializable(requireArguments(), ARG_TRACK, Track::class.java)!!
        rating = track.userRating ?: 0
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = mumaTrackInfoBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        bindHeader()
        bindNavigationRows()
        bindActions()
        bindFacts()
        bindTechnicalDetails()
        bindRating()
    }

    private fun bindHeader() {
        binding.trackInfoTitle.text = track.title ?: track.name.orEmpty()

        // The backdrop is the same artwork as the cover, blurred. The effect is set up front
        // rather than after loading, because it applies when the view draws, not when it binds.
        binding.trackInfoBackdrop.setRenderEffect(
            RenderEffect.createBlurEffect(BLUR_RADIUS, BLUR_RADIUS, Shader.TileMode.CLAMP)
        )

        imageLoaderProvider.executeOn {
            it.loadImage(binding.trackInfoCover, track, true, 0)
            it.loadImage(binding.trackInfoBackdrop, track, true, 0)
        }
    }

    private fun bindNavigationRows() {
        // Tapping through to the artist is a no-op without ID3 tags, so do not offer it.
        val artist = track.artist
        val showArtist = Settings.id3TagsEnabledOnline && !artist.isNullOrBlank()
        binding.trackInfoArtistRow.isVisible = showArtist
        binding.trackInfoArtistValue.text = artist

        val album = track.album
        val hasAlbumTarget = if (shouldUseId3Tags()) track.albumId != null else track.parent != null
        binding.trackInfoAlbumRow.isVisible = !album.isNullOrBlank() && hasAlbumTarget
        binding.trackInfoAlbumValue.text = album

        binding.trackInfoArtistRow.setOnClickListener { reportAction(R.id.menu_show_artist) }
        binding.trackInfoAlbumRow.setOnClickListener { reportAction(R.id.menu_show_album) }
    }

    private fun bindActions() {
        val online = !isOffline()

        binding.trackInfoActionLyrics.isVisible =
            online && track.artist != null && track.title != null
        binding.trackInfoActionShare.isVisible = online
        binding.trackInfoActionBookmark.isVisible = online
        binding.trackInfoActionBookmarkDelete.isVisible = online && track.bookmarkPosition > 0

        binding.trackInfoActionLyrics.setOnClickListener { reportAction(R.id.menu_lyrics) }
        binding.trackInfoActionShare.setOnClickListener { reportAction(R.id.menu_item_share_song) }
        binding.trackInfoActionBookmark.setOnClickListener {
            reportAction(R.id.menu_item_bookmark_set)
        }
        binding.trackInfoActionBookmarkDelete.setOnClickListener {
            reportAction(R.id.menu_item_bookmark_delete)
        }
        binding.trackInfoActionRefresh.setOnClickListener { reportAction(R.id.menu_refresh_track) }
    }

    private fun bindFacts() {
        val genres = track.genres?.filter { it.isNotBlank() }
            ?: listOfNotNull(track.genre?.takeIf { it.isNotBlank() })
        binding.trackInfoGenreRow.isVisible = genres.isNotEmpty()
        binding.trackInfoGenreGroup.removeAllViews()
        genres.forEach { genre ->
            binding.trackInfoGenreGroup.addView(
                Chip(requireContext()).apply {
                    text = genre
                    isClickable = false
                    isCheckable = false
                }
            )
        }

        val trackNumber = track.track
        val discNumber = track.discNumber
        val trackText = when {
            trackNumber == null -> null
            discNumber != null -> String.format(
                Locale.getDefault(),
                "%d · %s",
                trackNumber,
                getString(R.string.track_info_disc, discNumber)
            )
            else -> trackNumber.toString()
        }
        binding.trackInfoTrackRow.isVisible = trackText != null
        binding.trackInfoTrackValue.text = trackText

        // A full release date is more useful than the year, so prefer it when the server has one.
        val released = track.date?.takeIf { it.isNotBlank() } ?: track.year?.toString()
        binding.trackInfoReleasedRow.isVisible = released != null
        binding.trackInfoReleasedValue.text = released

        // Track durations are stored in seconds, unlike the player's own position readouts.
        val duration = track.duration
        binding.trackInfoDurationRow.isVisible = duration != null
        binding.trackInfoDurationValue.text = Util.formatTotalDuration(duration?.toLong())
    }

    private fun bindTechnicalDetails() {
        val bitRate = track.bitRate?.takeIf { it > 0 }
            ?.let { getString(R.string.song_details_kbps, it) }
        val format = track.suffix?.takeIf { it.isNotBlank() }
        val size = track.size?.takeIf { it > 0 }?.let { Util.formatBytes(it) }
        val summary = listOfNotNull(bitRate, format, size).joinToString(" · ")

        binding.trackInfoFormatValue.isVisible = summary.isNotEmpty()
        binding.trackInfoFormatValue.text = summary

        val path = track.path
        binding.trackInfoPathValue.isVisible = !path.isNullOrBlank()
        binding.trackInfoPathValue.text = path
        binding.trackInfoPathValue.setOnLongClickListener {
            copyToClipboard(path.orEmpty())
            true
        }

        // Nothing technical to show at all: drop the whole disclosure rather than open on empty.
        val hasDetails = summary.isNotEmpty() || !path.isNullOrBlank()
        binding.trackInfoTechToggle.isVisible = hasDetails
        binding.trackInfoTechToggle.setOnClickListener {
            val expanded = !binding.trackInfoTechBody.isVisible
            binding.trackInfoTechBody.isVisible = expanded
            binding.trackInfoTechChevron.rotation = if (expanded) 180f else 0f
        }
    }

    private fun copyToClipboard(text: String) {
        val clipboard = requireContext().getSystemService(Context.CLIPBOARD_SERVICE)
            as? ClipboardManager ?: return
        clipboard.setPrimaryClip(
            ClipData.newPlainText(getString(R.string.track_info_technical), text)
        )
        Toast.makeText(
            requireContext(),
            R.string.track_info_path_copied,
            Toast.LENGTH_SHORT
        ).show()
    }

    private fun bindRating() {
        stars().forEachIndexed { index, star ->
            star.contentDescription = getString(R.string.track_info_rate_stars, index + 1)
            star.setOnClickListener { setRating(index + 1) }
        }
        renderRating()
    }

    private fun setRating(newRating: Int) {
        rating = newRating
        track.userRating = newRating
        renderRating()
        setFragmentResult(
            RESULT_KEY,
            bundleOf(RESULT_TRACK to track, RESULT_RATING to newRating)
        )
    }

    private fun renderRating() {
        stars().forEachIndexed { index, star ->
            star.setImageResource(
                if (index < rating) R.drawable.ic_star_full else R.drawable.ic_star_hollow
            )
        }
    }

    private fun stars(): List<ImageView> = listOf(
        binding.trackInfoStar1,
        binding.trackInfoStar2,
        binding.trackInfoStar3,
        binding.trackInfoStar4,
        binding.trackInfoStar5
    )

    private fun reportAction(actionId: Int) {
        // Close first, then report: several of these actions navigate away, and doing that
        // while the sheet is still up leaves the dialog stranded over the new screen.
        val fragmentManager = parentFragmentManager
        dismiss()
        fragmentManager.setFragmentResult(
            RESULT_KEY,
            bundleOf(RESULT_TRACK to track, RESULT_ACTION_ID to actionId)
        )
    }
}
