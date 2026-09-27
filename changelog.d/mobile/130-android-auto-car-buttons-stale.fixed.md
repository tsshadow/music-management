- **The car's rating, shuffle, repeat and news buttons now follow the player** (issue #130, bug
  report 127). Diagnostics report 40 caught the car's session still holding "repeat off, no
  shuffle" 1.7 s after the car had set "repeat all" and the restored queue had made shuffle
  available. A repeat or queue change did not republish the buttons, so the car kept the old list
  until the next track change. The buttons are now republished on both, and the start-up list
  matches every later one. The `car sees` diagnostics line, written at 2 s and 15 s after Android
  Auto connects, now adds each button's slot, the commands granted to Android Auto, the playback
  state and whether each icon loads outside the app. The next report can then show why Android
  Auto 17.6 still draws none of the buttons (issue #131).
<!-- release notes -->
- Android Auto's extra buttons now keep up with repeat and shuffle changes. The diagnostics report
  records more about what the car receives, to track down why the car still does not show them.
