/*
 * ManualFragment.kt
 * Copyright (C) 2009-2026 Ultrasonic developers
 *
 * Distributed under terms of the GNU GPLv3 license.
 */

package nl.teunschriks.mumamobile.fragment

import android.app.Dialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import androidx.appcompat.app.AppCompatDialog
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.manual.ManualAdapter
import nl.teunschriks.mumamobile.manual.manualChapters
import nl.teunschriks.mumamobile.util.Util.applyTheme

/**
 * The in-app manual: what each screen is for, in reading order.
 *
 * Separate from About, which is version, changelog and bug report. Someone looking for "how do I
 * get my downloads offline" does not go looking under About, so Help is its own entry in the
 * overflow menu.
 */
class ManualFragment : Fragment() {

    private var screenshotDialog: Dialog? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        applyTheme(this.context)
        super.onCreate(savedInstanceState)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.manual, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        FragmentTitle.setTitle(this, getString(R.string.menu_help))

        val list = view.findViewById<RecyclerView>(R.id.manual_list)
        list.layoutManager = LinearLayoutManager(requireContext())
        list.adapter = ManualAdapter(
            chapters = manualChapters,
            onAction = { chapter ->
                chapter.actionDestination?.let { findNavController().navigate(it) }
            },
            onScreenshot = { chapter ->
                chapter.screenshot?.let { showScreenshot(it) }
            }
        )
    }

    private fun showScreenshot(drawable: Int) {
        val content = layoutInflater.inflate(R.layout.manual_screenshot_dialog, null)
        content.findViewById<ImageView>(R.id.manual_screenshot_full).setImageResource(drawable)

        val dialog = AppCompatDialog(requireContext())
        dialog.setContentView(content)
        content.setOnClickListener { dialog.dismiss() }
        dialog.show()
        // A dialog wraps its content by default, which on a tall screenshot leaves it as small as
        // it was in the list. Enlarging is the whole point of the tap, so take the window.
        dialog.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        )
        screenshotDialog = dialog
    }

    override fun onDestroyView() {
        // The dialog holds the fragment's context; leaving it up outlives the view it came from.
        screenshotDialog?.dismiss()
        screenshotDialog = null
        super.onDestroyView()
    }
}
