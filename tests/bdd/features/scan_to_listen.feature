Feature: A track on disk becomes a listen
  Every other suite proves one component in isolation: that LMS answers in the
  shape music-manager expects, that MariaDB accepts the SQL, that a function
  does what it says. None of them proves that a file appearing on disk ends up
  as something you played.

  This is that chain, and it is written out here rather than only in a docstring
  so that the steps and the description cannot drift apart: if a step below is
  deleted, the scenario stops mentioning it.

  Background:
    Given the test stack is running
    And the fixture track is on the music volume
    And LMS has scanned its library

  Scenario: A scanned track can be found over Subsonic and recorded as a listen
    When the scanner is asked to scan the library
    Then the track is in the library under its own file name

    When the mobile app searches for the track over the Subsonic API
    Then the Subsonic search returns the track
    # What is still missing here is playback: nothing streams a byte of the file,
    # so "can be found" is proven and "can be played" is not.

    When a listen is recorded for the track
    # Read back out of the answer to the request, not out of the listen history.
    Then the listen is matched to the track that was scanned
