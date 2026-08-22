Feature: A star set in the player reaches the library, and stays there
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

  So the first scenario is not "a rating arrives". It is "a rating arrives
  attached to the track that was scanned", which is the part that broke. The
  second is what happens to it afterwards, which is the part that broke worse.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And LMS has scanned its library

  Scenario: A star lands on the scanned track rather than on an LMS id
    When the listener rates the track 4 stars
    Then LMS reports the track as rated 4
    And music-manager has the rating against the track it scanned

    # Ratings are changed far more often than they are set, and the row is
    # written with ON DUPLICATE KEY -- a handler that only ever inserted would
    # look correct until the second time anyone touched a star.
    When the listener changes the rating to 1 star
    Then music-manager has the new rating against the same track

  # Ratings are keyed on the track's own identity, not on its path, so anything
  # that gives a file a new identity silently detaches everything hanging off the
  # old one. Rebuilding a library did exactly that in production and took 887
  # ratings with it, and the same key is what audio features hang from. The
  # tracks were all still there; nothing errored; the stars were simply gone.
  #
  # Scanning a file that has not changed must therefore be a no-op as far as
  # identity is concerned, and the scan is forced here so that "nothing changed"
  # cannot be achieved by skipping the file on its timestamp.
  Scenario: A rating outlives a rescan of the file it belongs to
    Given the track is rated
    When the file is scanned again from scratch
    Then the track kept the identity the rating hangs from
    And the rating is still readable against it
    And the library still holds one copy of the track
