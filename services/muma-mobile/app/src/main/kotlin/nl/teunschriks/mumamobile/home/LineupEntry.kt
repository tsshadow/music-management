package nl.teunschriks.mumamobile.home

/**
 * One entry on the lineup browse screen.
 *
 * @param value the lineup as the server names it: the path to its file without the extension.
 * @param label the last step of that path, which is what the card shows.
 * @param parent the path this entry sits under; only filled for a search hit, where the label
 *   alone ("RED") does not say which edition it came from.
 * @param hasChildren whether opening it means going a level deeper rather than playing tracks.
 * @param isAll whether it stands for the level itself -- "everything on Defqon.1 2014".
 */
data class LineupEntry(
    val value: String,
    val label: String,
    val parent: String = "",
    val hasChildren: Boolean = false,
    val isAll: Boolean = false
)
