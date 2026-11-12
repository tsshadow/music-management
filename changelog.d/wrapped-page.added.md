- **The web player has a Wrapped page: `/wrapped/<period>/<tab>`.** The You tab shows your own
  year as cards (top tracks, artists, genres, labels, festivals, tempo, your listening clock,
  streaks, ratings, your word of the year and more), the Library tab shows the year of every
  account together. Pick another year or a range of up to three years in the period menu. A card
  that counts only listens that matched a track says how many it left out, and the last card lists
  every card the server left out, with its reason. Each card has a share button: the image is
  1080 by 1920 and has no username and no server address in it. A browser that can share files
  opens its share dialog, any other browser saves the PNG. Wrapped is in the sidebar and in the
  library tab, and from 1 December to 31 January a tile on the home screen opens it (Settings >
  General can hide that tile). Every track in the Wrapped payload now also has `library_path`, the
  path LMS plays it by, so the play button on a track card works (`WRAPPED_FORMAT` 2; a tab
  stored in format 1 is computed again on its next open).

<!-- release notes -->

- **MuMa Wrapped in the web player.** Your year in music, and the library's, as a stack of cards
  you can share as an image. From 1 December a tile on the home screen opens it.
