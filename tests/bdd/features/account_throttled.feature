Feature: Ten wrong passwords lock the account, not the installation
  music-manager's login endpoint is the password check for every Subsonic
  request LMS serves, which makes it an oracle: anyone who can reach it can
  guess at leisure unless something counts the guesses. So it does, and after
  ten rejections in a minute the account stops answering -- even to the right
  password, because an account over its limit must stop being an oracle rather
  than keep confirming the one guess that was correct.

  What is counted is the point. The limit was first keyed on the caller's
  address, which for every Subsonic request is the LMS container: one bucket
  for the whole installation, and one phone with a stale password locked
  everyone out of the player at once. It is keyed on the account now, and the
  admin's line in the last scenario is what holds that in place.

  Background:
    Given the test stack is running
    And a listener "e2e-guesser" LMS knows but has never let in

  Scenario: An account under attack stops answering, and nobody else notices
    When the listener's password is guessed wrong ten times over the Subsonic API
    Then each guess was refused as a wrong password
    # The eleventh request does not reach the password at all: LMS relays
    # music-manager's 429 as a throttle, which is a different Subsonic error than
    # a wrong password -- a client can tell the two apart and stop retrying. LMS
    # only says "throttled" for a 429, so this line is also the proof that
    # music-manager sent one. It is not checked directly on purpose: the bucket
    # is the caller's address *and* the account, and this suite calls from the
    # host while LMS calls from its container, so a direct request from here
    # lands in a bucket nobody has touched and gets in.
    When the listener tries once more with the right password
    Then LMS reports the listener as throttled
    But the admin's own requests still go through
