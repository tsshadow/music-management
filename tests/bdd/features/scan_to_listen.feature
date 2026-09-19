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
    And nothing has been listened to yet

  Scenario: A scanned track can be found, played and recorded as a listen
    When the scanner is asked to scan the library
    Then the track is in the library under its own file name

    When the mobile app searches for the track over the Subsonic API
    Then the Subsonic search returns the track

    # The fixture is a 33 kbps mp3, the lowest of the five quality tiers. A
    # floor it clears has to list it and a floor it does not has to leave it
    # out: the first proves the scanner filed the track under a tier at all,
    # the second that the filter reads that tier rather than falling open.
    When the mobile app browses tracks of at least "low" quality
    Then the fixture track is listed
    When the mobile app browses tracks of at least "lossless" quality
    Then the fixture track is not listed

    When the mobile app streams the track
    Then the audio comes back whole and unconverted
    # Seeking, which is the only reason a player asks for part of a file. Worth
    # its own step because it is served by different code than a whole file is.
    And a player can ask for a single byte in the middle of it

    When a listen is recorded for the track
    Then the listen is matched to the track that was scanned
    # Not the same claim as the one above: that reads the answer to the request,
    # this reads what the server kept. Nothing serves an individual listen back,
    # so what is checked is that the count went from none to one.
    And the listen is in the library's own records
