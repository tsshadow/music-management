Feature: A playlist that filters on nothing offers the whole library
  Dynamic playlists are how the mobile app builds a queue: a handful of filters
  saved under a name, resolved against the library each time they are opened.
  The ones seeded for a new listener filter on a genre, or on nothing at all,
  and every one of them declares a rating range covering the whole scale as its
  way of saying "no rating filter".

  That range was once applied as a filter anyway. A track nobody has rated has
  no rating to compare, so it fell out, and a library of 302.561 tracks came back
  as the 1.221 that someone had starred. Nothing errored. The playlist was just
  short, in a way that only someone who knew how long it should be would notice.

  So the listener here is one who has never rated anything, and the claim is
  that the seeded playlist still offers them the track.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And a listener who has never rated anything

  Scenario: The seeded playlist offers a track nobody has rated
    When the listener's default playlists are seeded
    And the listener opens the playlist that filters on nothing
    Then the scanned track is in it
    And it is offered without a rating
