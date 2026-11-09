- **SECURITY.md said LMS's `/muma` proxy never sends MuMa the system key; three routes do.** The
  generic `/api/` proxy forwards the caller's own key, but per-user settings, an artist image and a
  track refresh go out with the system key once LMS checked the caller. The text now says so, and
  the proxy's verb mapping and the `/users/sync` rule have their own GTest cases (#228).
