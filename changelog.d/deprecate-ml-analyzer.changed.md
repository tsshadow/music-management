- **The ml-analyzer is deprecated and disabled; its code is kept.** It never ran in production (its
  compose service was commented out), nobody has time to work on it, and it would not have worked
  if it ran: the already-analysed check compares a track id against a path hash, the ML label rows
  are keyed by path hash while every reader joins them by track uid (bug report 028's shape), and
  `predict.py` feeds the model 11 unscaled audio features where the trainer fitted 41 scaled ones, into a
  table no deployed database has. It is now out of `backend:unit` and the coverage figure (the
  total goes up, the floor is untouched), out of `./build.sh`'s build-all run, the dependency audit
  and Renovate, and commented out of `docker/docker-compose.full.yml` too. Its tests run only in
  the manual job `backend:ml-analyzer-unit`, and `tests/ci/test_ml_analyzer_deprecated.py` fails if
  any other job picks it up again. `library_track_audio_features` and `library_track_ml_labels`
  keep their data, so BPM, analytics and feeds keep showing what is there; new tracks get no
  analysis. `services/ml-analyzer/DEPRECATED.md` has the defects with file and line and the
  checklist for reviving it.

<!-- release notes -->

- **The ML analyzer is switched off for now, not deleted.** It never ran in production and would
  not have worked. BPM and other analysis already in the library stays visible; new tracks get
  none until it is repaired.
