Feature: An edit made through the LMS proxy arrives with the verb it was sent with
  The web UI never talks to music-manager directly: every call goes through the
  LMS `/muma` proxy, which forwards the path, the key and the body. It did not
  forward the verb. Every PUT and DELETE left as a POST, so a route that only
  takes the real verb answered 405 -- editing a radio channel in Beheer was the
  one Teun hit, on production, and the browser reported a method error for a
  request it never sent.

  Nothing else in this suite would have caught it. Every other call the suite
  makes through the proxy is a GET or a POST, which is exactly why the bug lived
  as long as it did: those two are the verbs the proxy did handle.

  The radio channel is the route it broke on, but the check is about the proxy.
  Each step asserts the status music-manager answers with, because a 405 there
  says "wrong verb" and nothing else can.

  Background:
    Given the test stack is running

  Scenario: A channel is created, edited, read back and removed through the proxy
    When a radio channel is created through the LMS proxy
    Then the proxy answers that the channel was created
    When the channel is renamed through the LMS proxy
    Then the proxy answers with the renamed channel
    And the channel reads back under its new name
    When the channel is removed through the LMS proxy
    Then the proxy answers that the channel is gone
    And the channel no longer reads back
