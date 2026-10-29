Feature: A genre tag becomes something you can curate
  A file's genre does not travel straight into the library. The scanner maps
  tags onto curated genre rows and skips anything it has no row for, and the
  only thing that ever creates a row is the tagger. So a library scanned before
  its files were tagged has no genres at all, which looks exactly like a
  collection whose files carry no genre.

  A fresh database hides that. Every genre a new database is seeded with is blacklisted --
  they are the YouTube category names -- so before the tagger has run, no genre
  in any file resolves to anything, and the emptiness reads as the library
  having nothing to say rather than as a step that has not happened.

  The tagger runs when the stack is built, because it rewrites the files and
  both indexes have to be built from the finished bytes. What is left to walk
  here is the second half: a genre that is waiting for a decision, and a scan
  that puts tracks behind it.

  Background:
    Given the test stack is running
    And the fixture track is on the music volume
    And the fixture's genre is waiting for a decision
    And no track carries that genre yet

  Scenario: A queued genre gets its tracks once the library is scanned
    When the scanner is asked to scan the library
    Then the track carries its genre
    And the library lists that genre with the track against it
    # Still 'unknown'. The scanner attaches tracks to a genre; it never decides
    # about one, and a genre that curated itself would defeat the point of a
    # queue.
    And the genre is still waiting for a decision
