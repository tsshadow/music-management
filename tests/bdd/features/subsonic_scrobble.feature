Feature: A play reported through LMS reaches the library
  The chain in scan_to_listen.feature ends with a listen, but the listen is
  posted straight at music-manager. No client does that. The phone, the car and
  the web player all talk Subsonic to LMS, and LMS relays the play to
  music-manager from its own record of the track -- its own title, its own
  artist, the login name of whoever pressed play. That hop is the one that
  carries every real listen, and until here nothing walked it.

  It has failed before in ways the direct post cannot show: LMS coming up before
  music-manager and dropping the relay into a retry queue that never drained,
  and LMS's idea of a title disagreeing with music-manager's so that every play
  landed as unmatched. Both look like a working player and an empty history.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And LMS has scanned its library

  # Counters, because counters are all music-manager serves for listens; see
  # conftest.stats. Both are read, so a play that arrived but landed in the
  # unmatched table -- LMS and music-manager disagreeing about the track's name
  # -- fails on the second count rather than passing on the first.
  Scenario: A listen submitted over the Subsonic API is recorded as a match
    Given the number of listens on record is known
    When the mobile app submits the play over the Subsonic API
    Then LMS accepts the submission
    And music-manager has recorded one more listen
    And none of it was filed as unmatched
