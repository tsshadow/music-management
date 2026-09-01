Feature: A decision on a genre is kept, and reaches the files it touches
  genre_curation.feature stops at a genre waiting in the queue. This is the
  step after it: someone approves the genre. Three things have to follow from
  that, and each has silently not followed at some point. The genre must leave
  the queue, or it is decided on again tomorrow. The decision must be recorded
  as made by a person, or the tagger's next round overwrites it with its own
  guess. And the files carrying the genre must be marked for a retag, because
  the decision changes what the tagger would write and nothing else tells it.

  Approving rather than rejecting, deliberately. A rejected genre asks the
  tagger to strip it from the file, and the tagger's background round would
  oblige unasked -- rewriting the bytes that LMS has already indexed, which is
  exactly the disagreement scan_to_listen.feature's streaming steps assert
  against. An approval changes what is recorded about the file, not the file.

  Background:
    Given the test stack is running
    And music-manager has scanned the fixture track
    And the fixture's genre is waiting for a decision

  Scenario: An approved genre leaves the queue and keeps its tracks
    When the curator approves the genre
    Then the genre is no longer waiting for a decision
    And the decision is on record, so the tagger will not undo it
    And the library still lists the genre with the track against it
    # Marked, not retagged. The retag itself walks the whole library and rewrites
    # files, which is the tagger's job to prove and this stack's job to leave
    # alone; what this chain owns is that the mark was made and says why.
    And the track's file is queued for a retag because of the decision
