package nl.teunschriks.mumamobile.util

import java.util.Comparator
import java.util.SortedSet
import java.util.TreeSet

/**
 * A TreeSet that ensures it never grows beyond a max size.
 * `last()` is removed if the `size()`
 * get's bigger then `getMaxSize()`
 */
class BoundedTreeSet<E> : TreeSet<E> {
    private var maxSize = Int.MAX_VALUE

    constructor(maxSize: Int) : super() {
        setMaxSize(maxSize)
    }

    // The element-carrying constructors deliberately hand nothing to `super`: TreeSet's
    // own constructors call addAll(), which is overridden here and adjusts against a
    // maxSize that the property initializer has not run yet, so the bound reads as 0 and
    // the set trims itself to nothing. Set the bound first, then add.
    constructor(maxSize: Int, c: Collection<E>?) : super() {
        setMaxSize(maxSize)
        if (c != null) addAll(c)
    }

    constructor(maxSize: Int, c: Comparator<in E>?) : super(c) {
        setMaxSize(maxSize)
    }

    constructor(maxSize: Int, s: SortedSet<E>?) : super(s?.comparator()) {
        setMaxSize(maxSize)
        if (s != null) addAll(s)
    }

    fun getMaxSize(): Int = maxSize

    fun setMaxSize(max: Int) {
        maxSize = max
        adjust()
    }

    private fun adjust() {
        while (maxSize < size) {
            remove(last())
        }
    }

    override fun add(element: E): Boolean {
        val out = super.add(element)
        adjust()
        return out
    }

    override fun addAll(elements: Collection<E>): Boolean {
        val out = super.addAll(elements)
        adjust()
        return out
    }
}
