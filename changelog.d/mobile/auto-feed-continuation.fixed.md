- **A feed played from Android Auto continues past its first page** (issue #84). Near the end of a
  queue started from Release Radar or a daily mix in the car -- with "Alles afspelen" or a tapped
  track -- the app fetches the feed's next page (`next_offset`) and appends it to the queue, the
  same way the web player does. It stops when the server has no more, never appends a track the
  queue already holds (Release Radar is rebuilt hourly), and asks one page at a time. The car's
  feed folder itself still lists at most 100 tracks.
<!-- release notes -->
- Release Radar and the daily mixes in the car no longer stop after the first 100 tracks.
