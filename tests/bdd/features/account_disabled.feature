Feature: Disabling an account closes the player too
  LMS has no accounts of its own. music-manager owns them and pushes them
  across, and when the player presents a password LMS goes back to
  music-manager to ask whether it is still good. That round trip is the whole
  reason the arrangement holds: a listener switched off in one place has to be
  switched off everywhere, without anything being restarted or resynced.

  access_control.feature proves the API refuses a caller it does not know. This
  proves it refuses one it knows and has decided against, and that the refusal
  travels: LMS must not go on serving an account music-manager has closed by
  falling back to its own copy of the user.

  With one window, stated here because it is easy to mistake for the failure
  above. LMS remembers a password it has accepted for five minutes and does not
  ask again in that time -- the alternative was every request from every client
  blocking a server thread on the same round trip, which once took the whole
  site down. So an account that was in use keeps working on LMS for up to five
  minutes after being disabled. That is a decision, not a defect, and it is why
  the listener here is one LMS has been told about but has never let in: the
  first password it presents is the first one LMS has to ask about.

  Background:
    Given the test stack is running
    And a listener LMS knows but has never let in

  Scenario: An account disabled in music-manager is refused by LMS
    When the administrator disables the listener's account
    Then music-manager refuses the listener's password
    And LMS refuses the listener
    # Refusals are not remembered, so this is immediate: nothing here waits.
    When the administrator enables the account again
    Then LMS lets the listener in
