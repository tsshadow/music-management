- **Release Radar and the daily mixes held 30 tracks, often under an hour of music.** They now hold
  100 by default, and the length is a setting ("Feed length", Beheer -> Config -> Feeds, 10-200), so it
  can change without a release. Measured on production: five of the seven feeds reach 100 on their
  own, and a build of 100 costs the same as one of 30 (Release Radar 4.1 s both); only Middenin and
  Harder take about 22 s at 100, because they top up a few places from tracks of unknown hardness.
- **"Meer laden" at the end of a feed.** `GET /api/feeds/{slug}` takes `offset` and answers
  `next_offset`: the next page is the same day's feed built with more places, without any song
  already served, and it is stored so the same page asked twice holds the same tracks (at most 500
  per feed per day). The feed page shows a "Meer laden" button, and a queue started from a feed
  (the feed page or a Home card, web and app) tops itself up before it runs out. Both clients now
  resolve feed paths to songs in chunks of 100, the most LMS accepts per call.
<!-- release notes -->
- Release Radar and the daily mixes now hold 100 tracks instead of 30 (adjustable in Beheer), and a
  feed can be continued with "Meer laden"; playing a feed keeps going past its first 100 tracks.
