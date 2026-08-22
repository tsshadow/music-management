Feature: A star set in the player reaches the library
  Ratings are set in one place and one place only: the star lands on LMS, which
  pushes the change to music-manager. Nothing travels the other way, so if this
  hop fails the rating exists on exactly one side and nobody is told.

  The hop is harder than it looks because the two do not agree on what a file is
  called. LMS reports it under its own media root, music-manager stores it under
  the mount it scans, and the webhook has to recognise both as the same file. If
  it cannot, the handler falls back to LMS's own track id -- which stops meaning
  anything the moment LMS rebuilds its library, leaving a rating attached to a
  track that no longer exists. That is not a hypothetical: most of the mirrored
  ratings in production ended up keyed that way.

  So the scenario below is not "a rating arrives". It is "a rating arrives
  attached to the track that was scanned", which is the part that broke.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And LMS has scanned its library
    And the track has no rating yet

  Scenario: A star lands on the scanned track rather than on an LMS id
    When the listener rates the track 4 stars
    Then LMS reports the track as rated 4
    And music-manager has the rating against the track it scanned

    # Ratings are changed far more often than they are set, and the row is
    # written with ON DUPLICATE KEY -- a handler that only ever inserted would
    # look correct until the second time anyone touched a star.
    When the listener changes the rating to 1 star
    Then music-manager has the new rating against the same track
