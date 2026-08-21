package nl.teunschriks.mumamobile.fragment

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import androidx.viewpager2.widget.ViewPager2
import com.google.android.material.button.MaterialButton
import nl.teunschriks.mumamobile.R
import nl.teunschriks.mumamobile.wizard.SharedWizardPreferences
import nl.teunschriks.mumamobile.wizard.WizardPagerAdapter
import nl.teunschriks.mumamobile.wizard.chromeFor
import nl.teunschriks.mumamobile.wizard.plan
import nl.teunschriks.mumamobile.wizard.wizardCatalog

/**
 * The setup wizard. Opened after an update with the version the user came from, so steps added
 * since then lead and are badged, or from the overflow menu with no argument at all - in which
 * case the default below means nothing compares as new.
 */
class SetupWizardFragment : Fragment() {

    companion object {
        const val ARG_LAST_SEEN_VERSION = "lastSeenVersion"
    }

    private lateinit var pager: ViewPager2
    private lateinit var progress: TextView
    private lateinit var back: MaterialButton
    private lateinit var next: MaterialButton

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View = inflater.inflate(R.layout.fragment_setup_wizard, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        val lastSeen = arguments?.getInt(ARG_LAST_SEEN_VERSION, Int.MAX_VALUE) ?: Int.MAX_VALUE
        val steps = plan(wizardCatalog(requireContext()), lastSeen)

        pager = view.findViewById(R.id.wizard_pager)
        progress = view.findViewById(R.id.wizard_progress)
        back = view.findViewById(R.id.wizard_back)
        next = view.findViewById(R.id.wizard_next)

        pager.adapter = WizardPagerAdapter(
            steps = steps,
            prefs = SharedWizardPreferences(requireContext()),
            onJump = { destination -> findNavController().navigate(destination) }
        )

        pager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) = renderChrome(position, steps.size)
        })

        back.setOnClickListener { pager.currentItem = pager.currentItem - 1 }
        next.setOnClickListener {
            if (pager.currentItem == steps.size - 1) close() else pager.currentItem = pager.currentItem + 1
        }
        view.findViewById<MaterialButton>(R.id.wizard_skip).setOnClickListener { close() }

        renderChrome(pager.currentItem, steps.size)
    }

    private fun renderChrome(position: Int, count: Int) {
        val chrome = chromeFor(position, count)
        progress.text = getString(R.string.wizard_progress_format, position + 1, count)
        back.visibility = if (chrome.showBack) View.VISIBLE else View.INVISIBLE
        next.text = getString(if (chrome.isLastStep) R.string.wizard_done else R.string.wizard_next)
    }

    private fun close() {
        findNavController().popBackStack()
    }
}
