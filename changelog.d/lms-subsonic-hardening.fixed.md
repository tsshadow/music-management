- **Clearing a rating now clears it in MuMa too.** The server deleted its rating row and then
  reported the change by the id of the row it had just deleted, so nothing was ever sent and MuMa
  kept the old star forever. It now sends a `rating_removed` event (rating 0), captured before the
  row goes, and `POST /api/rating/lms-event` deletes the mirrored row on it -- and on a
  `rating_changed` of 0, which no star count means. A cross-app contract change: an older MuMa
  ignores `rating_removed`, so both sides ship together.
- **Deduplicated track pages no longer skip tracks.** `nextOffset` advanced past every row the last
  scan fetched, including the rows after the page had filled, so those tracks never appeared on
  any page. It now counts only the rows actually used. History also loads its listens and tracks
  in one query instead of one per listen.
<!-- release notes -->
- **Clearing a rating now also clears it in MuMa.**
- **Scrolling through versions-merged track lists no longer skips tracks.**
