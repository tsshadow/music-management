- **Listens from the app went missing, and LMS and MuMa disagreed about when they happened.** Bug
  report 071: of four listens LMS recorded on 2026-09-25, MuMa had one. The app's side is fixed in
  MuMa Mobile (a queue on the phone that keeps every listen until LMS confirms it); it now sends the
  play's start time as the Subsonic `time`, which LMS records and relays to MuMa unchanged, so a
  resend lands on the same `scrobble_listens` row and the reconcile pairs the two exactly. The three
  missing listens that morning had reached LMS and were dropped by its relay to MuMa, which gives up
  after two immediate retries; that part is not fixed here and is tracked in `docs/open-work.md`.

<!-- release notes -->

- **Listens from the app are no longer lost on the phone's side.** Listens LMS could not pass on to
  MuMa during a restart can still go missing; that is next.
