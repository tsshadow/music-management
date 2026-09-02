Feature: A rejected genre is taken out of the files that carry it
  genre_decision.feature approves a genre and stops at the mark it leaves: the
  file is queued for a retag. This is the other decision, and the whole loop
  behind it. Rejecting a genre says the tag itself is wrong -- a YouTube
  category, a typo, a label's idea of a style -- and the tagger is what puts
  that right, by rewriting the file. Then the scanner reads the file back, and
  then LMS does, and only after all three has the curator's click reached the
  player.

  Three components, three places to stop half-way, and each has. A decision
  that saved but never marked a file. A mark that was made but a tagger still
  resolving the genre the old way, from a rule table it loaded at startup. A
  file rewritten with nothing telling the player.

  Last in the run on purpose: this is the one feature that changes the fixture's
  bytes, and the streaming scenario compares what it gets to the size LMS
  indexed. Order is set in conftest.py.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And the track carries its genre

  Scenario: Rejecting a genre strips it from the file, the library and the player
    When the curator rejects the genre
    Then the track's file is waiting for a retag
    When the retag is run
    Then the retag queue drains
    And the track no longer carries the genre
    # music-manager does not tell LMS in this stack -- that needs a Subsonic key
    # configured on the manager side, which the test stack does not have -- so
    # the scan is asked for here, the way LMS's own schedule would.
    When LMS rescans its library
    Then LMS no longer reports the genre on the track
