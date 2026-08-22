Feature: The library is closed to callers who cannot prove who they are
  Every other scenario in this suite authenticates, and that is the blind spot:
  a change that stopped checking keys altogether would leave all of them green.
  Proving the door opens for the right key says nothing about who else it opens
  for, and nothing else here would notice.

  The key is the whole of the defence. There is no session and no network
  boundary in front of the API, and it has been wrong in production before: the
  compose file passed the key under a name the application did not read, and the
  service came up with no system key at all.

  Background:
    Given the test stack is running

  Scenario Outline: A request that cannot prove who it is gets nothing
    When the library is asked for its tracks <credentials>
    Then the request is refused as unauthenticated
    And no track data comes back

    Examples:
      | credentials            |
      | with no API key at all |
      | with an invalid key    |
      | with an empty key      |

  # The control. Without it a stack that refused everything -- a database that
  # never came up, a key that was never configured -- would satisfy every line
  # above and read as proof that the door is locked.
  Scenario: The key the rest of the suite uses is still accepted
    When the library is asked for its tracks with the system API key
    Then the tracks come back
