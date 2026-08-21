package nl.teunschriks.mumamobile.wizard

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.google.android.material.materialswitch.MaterialSwitch
import nl.teunschriks.mumamobile.R

/**
 * One page per step. A Choice opens a single-choice dialog instead of using a Spinner: a dialog
 * inherits the active style without a per-style widget style, and a Spinner does not.
 *
 * [onWritten] is called with the preference key after every write, because storing a value is not
 * always the whole change - see [applyWizardSideEffect], which is what production passes here.
 * It deliberately has no default: a hook that silently does nothing is the exact failure this
 * parameter exists to fix, so a caller that forgets it has to fail to compile instead.
 */
class WizardPagerAdapter(
    private val steps: List<PlannedStep>,
    private val prefs: WizardPreferences,
    private val onWritten: (String) -> Unit,
    private val onJump: (Int) -> Unit
) : RecyclerView.Adapter<WizardPagerAdapter.StepHolder>() {

    class StepHolder(view: View) : RecyclerView.ViewHolder(view) {
        val image: ImageView = view.findViewById(R.id.wizard_image)
        val title: TextView = view.findViewById(R.id.wizard_step_title)
        val badge: TextView = view.findViewById(R.id.wizard_new_badge)
        val body: TextView = view.findViewById(R.id.wizard_step_body)
        val toggle: MaterialSwitch = view.findViewById(R.id.wizard_toggle)
        val choice: MaterialButton = view.findViewById(R.id.wizard_choice)
        val jump: MaterialButton = view.findViewById(R.id.wizard_jump)
    }

    override fun getItemCount() = steps.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) = StepHolder(
        LayoutInflater.from(parent.context).inflate(R.layout.item_wizard_step, parent, false)
    )

    override fun onBindViewHolder(holder: StepHolder, position: Int) {
        val planned = steps[position]
        val step = planned.step
        val context = holder.itemView.context

        holder.title.text = context.getString(step.titleRes)
        holder.body.text = context.getString(step.bodyRes)
        holder.badge.visibility = if (planned.isNew) View.VISIBLE else View.GONE

        if (step.imageRes != null) {
            holder.image.setImageResource(step.imageRes)
            holder.image.visibility = View.VISIBLE
        } else {
            holder.image.visibility = View.GONE
        }

        holder.toggle.visibility = View.GONE
        holder.choice.visibility = View.GONE
        holder.jump.visibility = View.GONE

        when (val control = step.control) {
            is WizardControl.Toggle -> bindToggle(holder, control)
            is WizardControl.Choice -> bindChoice(holder, control)
            is WizardControl.Jump -> bindJump(holder, control)
        }
    }

    private fun bindToggle(holder: StepHolder, control: WizardControl.Toggle) {
        holder.toggle.visibility = View.VISIBLE
        // Clear first: a recycled switch still carries the previous step's listener, and setting
        // the checked state below would fire it against the wrong key.
        holder.toggle.setOnCheckedChangeListener(null)
        holder.toggle.isChecked = prefs.getBoolean(control.prefKey, control.default)
        holder.toggle.setOnCheckedChangeListener { _, checked ->
            prefs.putBoolean(control.prefKey, checked)
            onWritten(control.prefKey)
        }
    }

    private fun bindChoice(holder: StepHolder, control: WizardControl.Choice) {
        val context = holder.itemView.context
        val entries = context.resources.getStringArray(control.entriesRes)
        val values = context.resources.getStringArray(control.valuesRes)

        // The stored value can age out of the array - a release edits the options and a device
        // still carries the old one. Fall back to the default's label, and only to the first
        // entry if even that has gone; never to the raw value, which is a key or a number.
        fun label(): String {
            val stored = prefs.getString(control.prefKey, control.default)
            val index = values.indexOf(stored).takeIf { it >= 0 } ?: values.indexOf(control.default)
            return entries.getOrElse(index) { entries.firstOrNull() ?: control.default }
        }

        holder.choice.visibility = View.VISIBLE
        holder.choice.text = label()
        holder.choice.setOnClickListener {
            val selected = values.indexOf(prefs.getString(control.prefKey, control.default))
            AlertDialog.Builder(context)
                .setTitle(holder.title.text)
                .setSingleChoiceItems(entries, selected) { dialog, which ->
                    prefs.putString(control.prefKey, values[which])
                    holder.choice.text = entries[which]
                    dialog.dismiss()
                    // Last: a style or scale write recreates the activity from under this view.
                    onWritten(control.prefKey)
                }
                .show()
        }
    }

    private fun bindJump(holder: StepHolder, control: WizardControl.Jump) {
        holder.jump.visibility = View.VISIBLE
        holder.jump.setOnClickListener { onJump(control.destinationId) }
    }
}
