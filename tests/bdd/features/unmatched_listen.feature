Feature: A listen for something the library does not have
  Scrobbles arrive for tracks this library cannot place: a play from another
  device, a title tagged differently here than at the source, a typo. The wrong
  thing to do with those is to drop them, and the second wrong thing is to
  report them as a match.

  This is the branch of the scrobble endpoint the main chain never takes, and it
  is the one that carries the history: matching is exact on artist and title, so
  the unmatched table is where the great majority of imported listens have ended
  up. A change that quietly started reporting those as matched would lose them
  for good, because nothing would ever come back to re-link them.

  Background:
    Given the test stack is running
    And no unmatched listens have been recorded yet

  Scenario: A listen that matches nothing is kept rather than dropped
    When a listen is recorded for a track the library does not have
    Then the listen is not reported as a match
    And it is kept for re-matching later
