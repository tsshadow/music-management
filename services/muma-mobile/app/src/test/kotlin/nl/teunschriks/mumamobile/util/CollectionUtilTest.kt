package nl.teunschriks.mumamobile.util

import java.util.concurrent.TimeUnit
import nl.teunschriks.mumamobile.domain.Track
import org.amshove.kluent.`should be equal to`
import org.amshove.kluent.`should be greater than`
import org.amshove.kluent.`should be less than`
import org.amshove.kluent.`should be null`
import org.junit.Test

/**
 * The plain-JVM containers and comparators in the util package.
 */
class BoundedTreeSetTest {

    // The constructors taking a Collection or a SortedSet are not exercised here:
    // they hand their argument to TreeSet's constructor, which calls the overridden
    // addAll() before maxSize has been initialised, so the bound reads as 0 and the
    // set trims itself to nothing. Only the (maxSize) constructor is used in the app.

    @Test
    fun `a set below its bound keeps everything`() {
        val set = BoundedTreeSet<Int>(3)

        set.add(2)
        set.add(1)

        set.toList() `should be equal to` listOf(1, 2)
    }

    @Test
    fun `adding past the bound drops the last element`() {
        val set = BoundedTreeSet<Int>(2)

        set.add(1)
        set.add(2)
        set.add(3)

        set.toList() `should be equal to` listOf(1, 2)
    }

    @Test
    fun `a smaller element pushes a larger one out`() {
        val set = BoundedTreeSet<Int>(2)
        set.addAll(listOf(5, 6))

        set.add(1)

        set.toList() `should be equal to` listOf(1, 5)
    }

    @Test
    fun `adding a whole collection respects the bound`() {
        val set = BoundedTreeSet<Int>(2)

        set.addAll(listOf(4, 1, 3, 2))

        set.toList() `should be equal to` listOf(1, 2)
    }

    @Test
    fun `a set built with a comparator uses it for the ordering`() {
        val set = BoundedTreeSet<Int>(2, compareByDescending { it })

        set.addAll(listOf(1, 2, 3))

        set.toList() `should be equal to` listOf(3, 2)
    }

    @Test
    fun `lowering the bound trims what is already there`() {
        val set = BoundedTreeSet<Int>(4)
        set.addAll(listOf(1, 2, 3, 4))

        set.setMaxSize(2)

        set.getMaxSize() `should be equal to` 2
        set.toList() `should be equal to` listOf(1, 2)
    }
}

class LRUCacheTest {

    @Test
    fun `a stored value can be read back`() {
        val cache = LRUCache<String, String>(2)

        cache.put("a", "Angerfist")

        cache["a"] `should be equal to` "Angerfist"
    }

    @Test
    fun `an unknown key yields nothing`() {
        LRUCache<String, String>(2)["a"].`should be null`()
    }

    @Test
    fun `filling the cache evicts the least recently used entry`() {
        val cache = LRUCache<String, String>(2)
        cache.put("a", "Angerfist")
        Thread.sleep(2)
        cache.put("b", "Outsiders")
        Thread.sleep(2)
        // Touching "a" makes "b" the oldest.
        cache["a"]
        Thread.sleep(2)

        cache.put("c", "Radical Redemption")

        cache["b"].`should be null`()
        cache["a"] `should be equal to` "Angerfist"
    }

    @Test
    fun `clearing drops everything`() {
        val cache = LRUCache<String, String>(2)
        cache.put("a", "Angerfist")

        cache.clear()

        cache["a"].`should be null`()
    }
}

class TimeLimitedCacheTest {

    @Test
    fun `a value is readable until it expires`() {
        val cache = TimeLimitedCache<String>(1, TimeUnit.MINUTES)

        cache.set("Angerfist")

        cache.get() `should be equal to` "Angerfist"
    }

    @Test
    fun `an expired value is gone`() {
        val cache = TimeLimitedCache<String>()

        cache.set("Angerfist", 0, TimeUnit.MILLISECONDS)
        Thread.sleep(2)

        cache.get().`should be null`()
    }

    @Test
    fun `a fresh cache holds nothing`() {
        TimeLimitedCache<String>().get().`should be null`()
    }

    @Test
    fun `clearing drops the value before it expires`() {
        val cache = TimeLimitedCache<String>(1, TimeUnit.MINUTES)
        cache.set("Angerfist")

        cache.clear()

        cache.get().`should be null`()
    }

    @Test
    fun `a value can be given its own lifetime`() {
        val cache = TimeLimitedCache<String>(0, TimeUnit.MILLISECONDS)

        cache.set("Angerfist", 1, TimeUnit.MINUTES)

        cache.get() `should be equal to` "Angerfist"
    }
}

class ResettableLazyTest {

    @Test
    fun `the initializer runs once and the value is kept`() {
        var runs = 0
        val lazyValue = ResettableLazy { ++runs }

        lazyValue.value
        lazyValue.value

        runs `should be equal to` 1
    }

    @Test
    fun `resetting makes the next read initialize again`() {
        var runs = 0
        val lazyValue = ResettableLazy { ++runs }
        lazyValue.value

        lazyValue.reset()

        lazyValue.value `should be equal to` 2
    }

    @Test
    fun `the value is also reachable as a delegated property`() {
        val holder = object {
            val delegate = ResettableLazy { "Angerfist" }
            val name: String by delegate
        }

        holder.name `should be equal to` "Angerfist"
    }
}

class EntryByDiscAndTrackComparatorTest {

    private val comparator = EntryByDiscAndTrackComparator()

    private fun track(
        id: String = "1",
        album: String? = "Close Combat",
        discNumber: Int? = 1,
        trackNumber: Int? = 1,
        path: String? = "a.mp3"
    ) = Track(id = id, album = album, discNumber = discNumber, track = trackNumber, path = path)

    @Test
    fun `the album decides first`() {
        comparator.compare(track(album = "Amsterdam"), track(album = "Close Combat")) `should be less than` 0
    }

    @Test
    fun `an album that is not set sorts first`() {
        comparator.compare(track(album = null), track(album = "Close Combat")) `should be less than` 0
        comparator.compare(track(album = "Close Combat"), track(album = null)) `should be greater than` 0
    }

    @Test
    fun `two tracks without an album fall through to the disc`() {
        comparator.compare(
            track(album = null, discNumber = 2),
            track(album = null, discNumber = 1)
        ) `should be greater than` 0
    }

    @Test
    fun `within an album the disc decides`() {
        comparator.compare(track(discNumber = 1), track(discNumber = 2)) `should be less than` 0
    }

    @Test
    fun `a missing disc counts as the first one`() {
        comparator.compare(track(discNumber = null), track(discNumber = 1)) `should be less than` 0
    }

    @Test
    fun `within a disc the track number decides`() {
        comparator.compare(track(trackNumber = 2), track(trackNumber = 10)) `should be less than` 0
    }

    @Test
    fun `a missing track number counts as zero`() {
        comparator.compare(track(trackNumber = null), track(trackNumber = 1)) `should be less than` 0
    }

    @Test
    fun `identical positions fall back to the path`() {
        comparator.compare(track(path = "a.mp3"), track(path = "b.mp3")) `should be less than` 0
    }

    @Test
    fun `two identical tracks compare equal`() {
        comparator.compare(track(), track()) `should be equal to` 0
    }

    @Test
    fun `a missing path sorts before one that is set`() {
        comparator.compare(track(path = null), track(path = "a.mp3")) `should be less than` 0
        comparator.compare(track(path = "a.mp3"), track(path = null)) `should be greater than` 0
        comparator.compare(track(path = null), track(path = null)) `should be equal to` 0
    }
}
