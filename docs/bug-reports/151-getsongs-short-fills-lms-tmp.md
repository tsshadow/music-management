# getSongs For Short Tracks Fills The LMS /tmp

# status: fixed

# reported problem
In Android Auto, Songs > "Recent toegevoegd" and Songs > "Recent uitgebracht" opened as empty
lists (2026-10-22). The same two rows under Sets worked.

The reverse-proxy log showed the request each row sends, and its answer:

    GET /rest/getSongs.view?clusters=[{"name":"LENGTH","value":"short"}]&count=500
        &sortMethod=AddedDesc&canonicalOnly=true ...  500 5

The same request with `"value":"long"` answered 200 with 543 kB. A short request that also had a
genre filter answered 200. LMS logged:

    Uncaught exception from handleRequest (aborting request): Sqlite3: SELECT DISTINCT t."id" ...
    FROM track t JOIN track_cluster tc0 ON tc0.track_id = t.id AND tc0.cluster_id IN (?) ...
    ORDER BY t.file_added DESC limit ?: database or disk is full

The app catches the error in `callWithErrorHandling` and gives the car an empty list, so the car
showed no error.

# Possible reason
`Track::find_advanced` joined `track_cluster` once per filter group. A join repeats a track for
each cluster it matches in the group, so the query was `SELECT DISTINCT t`. SQLite builds that
DISTINCT in a temporary B-tree from every matching row, with all 42 columns, before it applies
ORDER BY and LIMIT. For `LENGTH=short` the matching rows are nearly the whole library.

The LMS container has a read-only root file system and a 64 MB tmpfs on `/tmp`, so SQLite has no
other place for its temporary files. The B-tree did not fit and SQLite returned `SQLITE_FULL`.
A long-track request, or a short request with a genre, matches a few thousand rows, which fit.

A reproduction on a synthetic library of 250,000 tracks (88% short, rows widened to about 300
bytes) with a 64 MB heap limit fails for `short` with both sort methods, and passes for `long`.

# solution
- Each cluster group is now an `EXISTS (SELECT 1 FROM track_cluster ... )` condition in the WHERE
  clause (`appendClusterGroups` in `src/libs/database/impl/objects/Track.cpp`). A track passes
  once, whatever the number of clusters it matches, so the query needs no DISTINCT. SQLite then
  reads the rows in sort order and stops at the limit, or keeps only the top N rows for a sort
  that has no index.
- `find_advanced` keeps `SELECT DISTINCT` only when a join can still repeat a track: an artist
  filter (one link row per link type) or a rating user (`rated_track` has no unique key on user
  and track). `countAdvanced` keeps `COUNT(DISTINCT t.id)`, which holds only ids.
- `Track_findAdvanced_clusterGroupsReturnEachTrackOnce` in `src/libs/database/test/Track.cpp`
  checks that a track in two genres of one group comes back once, also on a page of one, and
  that the groups still AND together.
- The 64 MB `/tmp` stays. A query that needs more temporary space than that is a query to fix.
