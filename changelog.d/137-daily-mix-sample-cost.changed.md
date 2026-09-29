- **"Meer laden" on a daily mix no longer rebuilds the mix, and building one is 2-3x cheaper.**
  Klassiek, Zachter, Middenin, Harder and the label mix now rank 500 places in the same build and
  store everything past the first page, so the next page is read from the stored row instead of
  sampling the library twice again (about 11 s of queries on production). The samples themselves
  were slow because every feeds query grouped the whole audio-features table per scanned track to
  find a release date that `library_tracks` already had; they read it per track only when needed
  now -- recent half 4.8 s to 1.7 s, older half 6.1 s to 2.7 s, measured on production (issue #137).
<!-- release notes -->
- **"Load more" on a daily mix is instant.** The next page is ready instead of the mix being rebuilt,
  and building a daily mix is two to three times faster.
