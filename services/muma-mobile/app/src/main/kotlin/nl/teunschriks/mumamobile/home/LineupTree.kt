package nl.teunschriks.mumamobile.home

/**
 * One level of the lineup tree, out of the flat list `getLineups` answers with.
 *
 * A lineup's name is the path to its file -- "Defqon.1/2014/RED" -- and every directory on that
 * path is itself a lineup holding everything below it. The server therefore reports the stage, the
 * edition and the festival as three separate entries, which as one grid is a few hundred cards of
 * mostly repetition. This returns the direct children of [path] instead.
 *
 * Inside a level, the level itself comes first as an "all" entry, because "Defqon.1/2014" is a
 * lineup in its own right and would otherwise be unreachable once its stages are listed. At the
 * root that entry is left out: there is no lineup above the festivals.
 *
 * A non-empty [query] ignores the level and looks at every lineup there is, because a name is
 * easier to type than to navigate to.
 */
fun lineupLevel(names: List<String>, path: String, query: String = ""): List<LineupEntry> {
    val terms = query.trim().lowercase().split(WHITESPACE).filter { it.isNotEmpty() }

    if (terms.isNotEmpty()) {
        return names
            .filter { name -> terms.all { term -> name.lowercase().contains(term) } }
            .sortedBy { it.lowercase() }
            .map { name ->
                LineupEntry(value = name, label = lastStep(name), parent = parentLineup(name))
            }
    }

    val prefix = if (path.isEmpty()) "" else "$path/"
    val children = linkedMapOf<String, Boolean>()
    names.asSequence()
        .filter { prefix.isEmpty() || it.startsWith(prefix) }
        .map { it.removePrefix(prefix) }
        .filter { it.isNotEmpty() }
        .forEach { rest ->
            val value = prefix + rest.substringBefore('/')
            // A child that is only ever seen with something behind it is a directory.
            children[value] = (children[value] ?: false) || rest.contains('/')
        }

    val entries = children
        .toList()
        .sortedBy { (value, _) -> value.lowercase() }
        .map { (value, hasChildren) ->
            LineupEntry(value = value, label = value.removePrefix(prefix), hasChildren = hasChildren)
        }

    if (path.isNotEmpty() && names.contains(path)) {
        return listOf(LineupEntry(value = path, label = lastStep(path), isAll = true)) + entries
    }

    return entries
}

/** The level above [path], or "" when it is already a festival. */
fun parentLineup(path: String): String = path.substringBeforeLast('/', missingDelimiterValue = "")

private fun lastStep(path: String): String = path.substringAfterLast('/')

private val WHITESPACE = Regex("\\s+")
