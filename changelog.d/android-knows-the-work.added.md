- **`getSongs` accepteert nu `workId`,** zodat ook de app alle versies van één nummer kan opvragen.
  Die filter zat alleen in `getSpotifyTracks`, en de app bladert via `getSongs` — een versielijst die
  alleen de web-UI kon opvragen zou de telefoon een canonical laten tonen waar hij niet langs kan
  kijken.
