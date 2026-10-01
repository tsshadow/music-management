# A Scoped LMS Scan Of One File Recomputes The Whole Library

# status: fixed

# reported problem
GitLab issue #154. Measured on production on 2026-10-01 between 04:41 and 04:45 UTC (0.87.x):

- `GET /rest/getSpotifyTracks?sort=recent&deduplicate=true&minRating=2&includeUnrated=true&maxDuration=10&count=200`,
  the web player's default track list, answered in about 1.3 s while LMS was idle and in 12 to
  17 s while it was scanning.
- LMS was scanning most of the time. `docker logs lms` showed a scoped scan
  (`[UI] User 'user' requested a scan`) roughly every 40 to 90 s, about 50 requests and 42 scans
  an hour. Each scan read one changed file (`Changes = 1 ... Scanned = 1`) and still took 40 to 50 s.
  So the web UI was slow for well over half of every hour.

# Possible reason
Read-only measurements on production (192.0.2.27):

- `getScanStatus` was polled every 0.25 s from inside the music-manager container across five
  scoped scans. The time per step was about the same every time. ScanFiles, the removed-files
  check and ArtistReconciliation finished between two polls. The rest:

  | step | time | what it walks |
  |---|---|---|
  | AssociatePlayListTracks (+ UpdateLibraryFields) | 6 s | all 49,185 playlist files |
  | AssociateReleaseImages | 7.6 s | all 54,019 releases |
  | AssociateArtistImages + AssociateMediumImages | 5 s | all 55,627 artists, 54,166 mediums |
  | AssociateTrackImages | 18 s | all 343,538 tracks (`totalCount` in the status) |
  | ComputeClusterStats | 4.5 s | all 39,110 clusters, two COUNT queries each |

  That adds up to 41 s of a 42 s scan.
- Each of these steps runs when `context.stats.getChangesCount() > 0` and then walks the whole
  table by id range. The scope of the scan (`ScanOptions::scanDirectories`) is never looked at.
  Upstream LMS designed them for library-wide scans. The fork added scoped scans (bug report 126)
  and limited the walk, the removed-files check, the duplicate report and ANALYZE to the scope. The
  association steps and the cluster counts were left library-wide. Bug report 136 measured the same
  48-56 s for an idle scoped scan and did not change it.
- music-manager is not the lever. The requests come from the downloader workers' `announce()`,
  one per downloaded file, and a download lands about once a minute. LMS's own collector already
  merges requests (5 s quiet period, 60 s cap). A MuMa-side window wide enough to merge one-a-minute
  requests would hold every new download back by minutes, and each scan would still cost 42 s.
- The endpoint has a cost of its own, which grows under that contention. On a copy of production's
  `lms.db` (2026-09-30) its query, `SELECT DISTINCT t ... ORDER BY COALESCE(t.original_date, t.date)
  DESC, t.release_id, m.position, t.track_number LIMIT 201`, is `SCAN t` + `USE TEMP B-TREE FOR ORDER BY`
  and takes 0.65 s. The deduplicated page usually runs it twice (`collectDedupedPage`).
  No index matches the sort expression.

# solution
LMS (`services/music-management-server`):

- **Scoped association.** A new `ScanScope` (`scanner/impl/steps/ScanScope.*`) is computed once
  per scoped scan, by the first step that asks for it, after the walk and the removed-files check.
  It holds:
  - every track under the scanned folders, plus the other tracks of their releases;
  - those tracks' releases, mediums, artists (any link type) and clusters;
  - the playlist files under the folders.

  AssociatePlayListTracks, AssociateReleaseImages, AssociateArtistImages, AssociateMediumImages
  and AssociateTrackImages walk only those ids, in runs of consecutive ids, so no id outside the
  scope is read. ComputeClusterStats recomputes the scope's clusters, plus every cluster whose
  cached track count no longer matches its `track_cluster` rows
  (`Cluster::findIdsWithOutdatedTrackCount`, one GROUP BY, 0.2 s on production's 2.1 million
  rows). That plus set covers the genre a retagged track left and the one a removed track was in.
  A library-wide scan is unchanged.
- **Fallbacks to library-wide.** A scope of more than 20,000 tracks (`maxScopedTrackCount`) is
  handled library-wide. So is a changed `artistImageFallbackToRelease` or
  `skipSingleReleasePlayLists` setting, and a cluster-count write the previous scan could not
  commit.
- **What waits for the next library-wide scan:**
  - an entity outside the folders whose artwork was an image the scan deleted (the foreign key has
    already set it to NULL, so it shows no artwork, not a broken one);
  - a release elsewhere that would pick up an image named after its MBID in a scanned folder;
  - a playlist elsewhere that lists a file from a scanned folder.
- **An index for the sort.** `track_filing_date_release_idx ON track(COALESCE(original_date, date)
  DESC, release_id)`, created by `Session::createIndexesIfNeeded()` on every start, so no
  migration and no database version bump. On the production copy the endpoint's query drops from
  0.65 s to 2 ms, with or without DISTINCT, at offset 0 and at offset 200. SQLite walks the index
  and sorts only the last two terms of a page.

music-manager is unchanged, for the reason above.

Expected after deploy: a one-file scoped scan should take a second or two instead of 42 s, so LMS
should be scanning a few percent of the hour instead of most of it. The page should take what its
serialisation takes, without the 2 x 0.65 s of sorting, whether or not a scan runs. This is still to
be measured on production: GitLab issue #155.

Tests: `test-scanner` `ScanScope.*`:
- the scope covers the folder and the rest of its releases, and not a sibling with the same name
  prefix;
- more than the cap falls back to library-wide;
- scoped track artwork leaves tracks outside the scope alone, and library-wide still reaches them;
- scoped cluster stats also fix the genre a retagged track left;
- `toConsecutiveIdRanges`.

`test-database`:
- `Cluster_findIdsWithOutdatedTrackCount`;
- `Track_originalDateSortWalksItsIndex` (EXPLAIN QUERY PLAN names the new index).
