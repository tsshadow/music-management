package nl.teunschriks.mumamobile.data

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Query
import nl.teunschriks.mumamobile.domain.Track

@Dao
@Entity(tableName = "tracks")
interface TrackDao : GenericDao<Track> {
    /**
     * Clear the whole database
     */
    @Query("DELETE FROM tracks")
    fun clear()

    /**
     * Get all albums
     */
    @Query("SELECT * FROM tracks")
    fun get(): List<Track>

    /**
     * One track, by the id the server gave it.
     *
     * The primary key is (id, serverId) and this deliberately ignores the server: a database is
     * already per-server (see `ActiveServerProvider.getActiveMetaDatabase`), so within one there
     * is at most one row per id, and the caller -- the Capacitor bridge resolving a track id the
     * web player handed it -- has no server id to pass.
     */
    @Query("SELECT * FROM tracks WHERE id = :id LIMIT 1")
    fun byId(id: String): Track?

    /**
     * The same lookup as [byId] for a whole list, in one statement.
     *
     * A track list on the web player asks for the download state of every row it draws, which is
     * two hundred ids on one screen. Two hundred round trips through Room is not the same cost as
     * one `IN (...)`, and the caller has no way to spread them out. Callers chunk to stay under
     * SQLite's host-parameter limit; see `TrackLookup.fromCache`.
     */
    @Query("SELECT * FROM tracks WHERE id IN (:ids)")
    fun byIds(ids: List<String>): List<Track>

    /**
     * Get albums by artist
     */
    @Query("SELECT * FROM tracks WHERE albumId LIKE :id")
    fun byAlbum(id: String): List<Track>

    /**
     * Get albums by artist
     */
    @Query("SELECT * FROM tracks WHERE artistId LIKE :id")
    fun byArtist(id: String): List<Track>

    /**
     * Filter tracks by optional parameters and order the result.
     *
     * @param genre optional genre to filter by
     * @param year optional year to filter by
     * @param minDuration optional minimum duration in seconds
     * @param maxDuration optional maximum duration in seconds
     * @param minRating optional minimum user rating
     * @param maxRating optional maximum user rating
     * @param sortBy optional field to sort the result by. Defaults to title
     * @param limit max number of results to return
     * @param offset number of results to skip
     */
    @Query(
        """
            SELECT * FROM tracks
            WHERE (:genre IS NULL OR genre LIKE :genre)
              AND (:year IS NULL OR year = :year)
              AND (:minDuration IS NULL OR duration >= :minDuration)
              AND (:maxDuration IS NULL OR duration <= :maxDuration)
              AND (:minRating IS NULL OR userRating >= :minRating)
              AND (:maxRating IS NULL OR userRating <= :maxRating)
            ORDER BY
                CASE
                    WHEN :sortBy = 'album' THEN album
                    WHEN :sortBy = 'artist' THEN artist
                    WHEN :sortBy = 'year' THEN year
                    WHEN :sortBy = 'duration' THEN duration
                    WHEN :sortBy = 'rating' THEN userRating
                    ELSE title
                END
            LIMIT :offset,:limit
        """
    )
    fun filterTracks(
        genre: String? = null,
        year: Int? = null,
        minDuration: Int? = null,
        maxDuration: Int? = null,
        minRating: Int? = null,
        maxRating: Int? = null,
        sortBy: String? = null,
        limit: Int,
        offset: Int = 0
    ): List<Track>
}
