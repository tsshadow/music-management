/*
 * VoiceCommandsFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.util.Util.applyTheme

/**
 * Lists what the voice search understands.
 *
 * The parser behind it takes far more than a title -- a genre, an artist, a label, a year, an
 * order and the favourites, in any combination -- and none of that is discoverable by talking to
 * the car and hoping. This page is where the wording lives; see
 * [nl.teunschriks.mumamobile.voice.VoiceQuery] for what actually reads it.
 */
class VoiceCommandsFragment : Fragment() {

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme(this.context)
        super.onCreate(savedInstanceState)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.voice_commands, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, getString(R.string.voice_title))
    }
}
