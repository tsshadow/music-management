- **The LMS log no longer carries an ERROR every 30 seconds from its own healthcheck.** The probe
  called `/rest/ping.view` without credentials, which LMS logged as "Required parameter 'c' is
  missing" 2,880 times a day. It now asks `getOpenSubsonicExtensions`, the one Subsonic call that
  needs no login, and still only checks that an HTTP thread answers.
