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

  Scenario: A scanned track can be found over Subsonic and recorded as a listen
    When the scanner is asked to scan the library
    Then the track is in the library under its own file name

    When the mobile app searches for the track over the Subsonic API
    # Only that the query is answered. LMS keeps its own index and nothing here
    # triggers its scan, so the fixture is on its disk without being in its
    # library -- asserting on the results needs an LMS scan in the fixture step
    # first. The gap is real and this scenario is the place it is written down.
    Then the Subsonic search is answered

    When a listen is recorded for the track
    Then the listen is matched to the track that was scanned
