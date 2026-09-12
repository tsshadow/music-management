package nl.teunschriks.mumamobile.capacitor

import androidx.room.Room
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import nl.teunschriks.mumamobile.app.UApp
import nl.teunschriks.mumamobile.data.ActiveServerProvider
import nl.teunschriks.mumamobile.data.MetaDatabase
import nl.teunschriks.mumamobile.data.TrackDao
import nl.teunschriks.mumamobile.domain.Track
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import org.amshove.kluent.shouldBeEqualTo
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * The two things the storage bridge has to get right that are not response shapes: how many
 * queries a screenful of rows costs, and whether the app thinks it can reach the server.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = UApp::class)
class OfflineStorageBridgeTest {

    private lateinit var database: MetaDatabase
    private lateinit var dao: TrackDao
    private lateinit var lookup: TrackLookup

    @Before
    fun setUp() {
        database = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), MetaDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        database.trackDao().set((1..ROWS).map { Track(id = "tr-$it", serverId = 1, title = "Track $it") })

        // A mock over the real DAO rather than the real one: the point of these tests is how
        // many statements a screenful of rows costs, and only a mock can count them.
        val real = database.trackDao()
        dao = mockk<TrackDao>()
        every { dao.byIds(any()) } answers { real.byIds(firstArg()) }
        every { dao.byId(any()) } answers { real.byId(firstArg()) }

        val meta = mockk<MetaDatabase>()
        every { meta.trackDao() } returns dao
        val provider = mockk<ActiveServerProvider>()
        every { provider.getActiveMetaDatabase() } returns meta
        lookup = TrackLookup(mockk<MediaPlayerManager>(relaxed = true), provider)
    }

    @After
    fun tearDown() = database.close()

    /**
     * A track list on the web player asks for the state of every row it draws. Two hundred ids
     * used to be two hundred `byId` statements; the glyphs are not worth that, and the call
     * happens on every scroll.
     */
    @Test
    fun `resolving two hundred ids costs one query`() {
        val ids = (1..LIST_SIZE).map { "tr-$it" }

        val found = lookup.fromCache(ids)

        found.size shouldBeEqualTo LIST_SIZE
        found["tr-7"]?.title shouldBeEqualTo "Track 7"
        verify(exactly = 1) { dao.byIds(any()) }
        verify(exactly = 0) { dao.byId(any()) }
    }

    /** Longer than SQLite takes host parameters, so it has to be split rather than refused. */
    @Test
    fun `a list longer than the statement limit is chunked, not dropped`() {
        val ids = (1..ROWS).map { "tr-$it" }

        lookup.fromCache(ids).size shouldBeEqualTo ROWS

        verify(exactly = 2) { dao.byIds(any()) }
    }

    @Test
    fun `an id this device has never seen is left out rather than failing the batch`() {
        val found = lookup.fromCache(listOf("tr-1", "tr-does-not-exist"))

        found.keys shouldBeEqualTo setOf("tr-1")
    }

    // -------------------------------------------------------------------- isOffline

    /**
     * Both halves of the app's own test. The listener can pick the offline library on a perfect
     * connection, and a phone in a tunnel has picked nothing -- either one means the web UI must
     * read the downloaded library instead of the server.
     */
    @Test
    fun `there is a route only when a network is up and a real server is selected`() {
        hasRouteToServer(activeServerIsOfflineDb = false, networkHasInternet = true) shouldBeEqualTo true
        hasRouteToServer(activeServerIsOfflineDb = false, networkHasInternet = false) shouldBeEqualTo false
        hasRouteToServer(activeServerIsOfflineDb = true, networkHasInternet = true) shouldBeEqualTo false
        hasRouteToServer(activeServerIsOfflineDb = true, networkHasInternet = false) shouldBeEqualTo false
    }

    private companion object {
        const val LIST_SIZE = 200

        /** One more than [TrackLookup.SQLITE_VARIABLE_LIMIT], so the chunking has to happen. */
        const val ROWS = TrackLookup.SQLITE_VARIABLE_LIMIT + 1
    }
}
