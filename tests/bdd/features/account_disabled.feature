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

  LMS remembers a password it has accepted for five minutes and does not ask
  again in that time -- the alternative was every request from every client
  blocking a server thread on the same round trip, which once took the whole
  site down. For a while that meant an account in use kept working on LMS for
  up to five minutes after being disabled, and the first version of this
  feature could only prove the lockout for an account LMS had never let in.
  Disabling now pokes LMS's user sync, and a sync makes LMS forget every
  password it had accepted. The second scenario is the one that holds that.

  Background:
    Given the test stack is running

  Scenario: An account disabled in music-manager is refused by LMS
    Given a listener "e2e-locked" LMS knows but has never let in
    When the administrator disables the listener's account
    Then music-manager refuses the listener's password
    And LMS refuses the listener
    # Refusals are not remembered, so this is immediate: nothing here waits.
    When the administrator enables the account again
    Then LMS lets the listener in

  # The listener here is one LMS has already served, so its password sits in
  # the cache with minutes left on it. Without the sync poke this scenario
  # would pass only by waiting those minutes out; with it, the very next
  # request is refused.
  Scenario: An account that is already in use is refused on its next request
    Given a listener "e2e-active" LMS knows but has never let in
    And LMS has let the listener in
    When the administrator disables the listener's account
    Then LMS refuses the listener
    When the administrator enables the account again
    Then LMS lets the listener in
