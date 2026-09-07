Feature: An imported release picks up what only its folders and its label know
  scan_to_listen.feature walks a file that already carries everything it needs. This
  is the other arrival: a scene rip of a label release, which turns up with a title,
  one artist tag holding two names, and a bare year. No label, no catalogue number,
  no genre. Everything the library ends up showing has to be worked out from the
  folders it was moved into and from rules a curator wrote.

  It is written as a chain rather than as unit tests because the hole it covers could
  not be seen from inside one. Every rule under services/tagger/Song/rules/ had a test
  of its own and passed it, and InferGenreFromLabelRule was in no song type's rule
  list at all -- 49 curated rows in rules_label_genre that nothing on production ever
  read. A test that asks a rule what it does cannot notice that nobody asks it.

  What this cannot assert, and it is worth being plain about it: the release date the
  NFO carries. The tagger writes it to the file as ORIGINALDATE and LMS reads it, but
  no music-manager endpoint serves it, so there is nothing here to compare against.
  That claim lives in services/tagger/Song/LabelSongTest.py instead.

  Background:
    Given the test stack is running
    And a scene release by "Lil Texas & Albino" is sitting under the label folder "Texcore"
    And curation has already accepted the genres "Uptempo Hardcore" and "Hardcore"

  Scenario: A release with no genre of its own gets the one its label carries
    # Both rules go in over the API, which is what refreshes the maps the running
    # tagger reads. Writing them straight into the database would leave the process
    # answering from what it preloaded at startup, and the scenario would pass or fail
    # on a cache expiry rather than on the rule.
    When the curator records that the label "Texcore" releases "Uptempo Hardcore"
    And the curator records that "Uptempo Hardcore" rolls up into "Hardcore"
    And the tagger is asked to tag the release
    And the scanner is asked to scan the library

    Then the release is in the library under the folder it was placed in
    And the label above it on disk is the label on the track
    # The artist tag held one string. Two names is what the library indexes on.
    And both artists are in the library as names of their own
    # And this is the string the tag actually said, which is what a reader wants shown
    # and what splitting would otherwise throw away.
    And the artist line as the file wrote it is kept as the display artist
    # The release carries no genre tag at all, so the label rule is the only thing
    # that could have put one there.
    And the genre its label carries is on the track
    # Both, not one: the broader genre is what a browse groups on and the subgenre is
    # what the record is, and each answers a question the other cannot.
    And the broader genre it rolls up into is on the track as well
