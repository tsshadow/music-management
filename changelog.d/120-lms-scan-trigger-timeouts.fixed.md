- **LMS's library-wide scan can finish again, and MuMa's scan requests stop timing out** (issue
  #93, bug report 120). The tagger asked LMS for a library-wide scan after every round, every ~5
  minutes, and LMS answered each request by aborting the scan it was running -- on the request's
  own thread, so the request waited for the abort and often ran past its ten-second timeout
  (~50 "Failed to trigger LMS scan ... Read timed out" WARNINGs per 12 hours). A library-wide scan
  takes most of an hour, so none ever completed; on 2026-09-27 two in a row were aborted at 152k
  and 650k file checks. LMS now lets a plain library-wide request join a scan that is already
  running (or run right after a scoped one) and answers at once; only `fullScan`, `forceOptimize`
  and `compact` still start over. Authentication no longer waits behind a scanner write batch just
  to stamp a token's last use or a user's last login, which is what timed out the downloader's
  folder notifications (~43 per 12 hours). The tagger round no longer sends a library-wide
  request -- every folder it writes is already announced -- and "rerun parse" announces the track's
  folder instead. A request that fails is retried once, and then carried to the next one instead
  of dropped; an LMS outage is one WARNING, not one per request.
<!-- release notes -->
- New and retagged music reaches the app without restarting the music server's library scan every
  five minutes, and the "Failed to trigger/notify LMS" alerts are gone.
