- **`__Free&None`, `__TODO` and release folder names no longer become a label** (bug report 146).
  Production LMS listed 236 releases under `__Free&None`/`___Free&None`, 29 under `__TODO`, and
  371 "labels" that were a release folder's name (`STH685RMXBP - Bassjackers_-_...-SINGLE-WEB-2026-SRG`).
  The label is read from the folder a release is filed in, and the importer filed `FREE ...`
  releases into `__Free&None` and then tagged them with that folder as their publisher, without
  asking whether it was a label. One predicate now decides it for the tagger, the importer's
  label proposals and the scanner: a name starting with `_`, the import queue's name, or a name
  shaped like a scene release folder is never a label. A release in `__Free&None` gets no label at
  all, and a retag removes one it already carries. Real labels such as `DWX Copyright Free`,
  `Freestyle` and `I AM HARDSTYLE - Amplify` are unaffected.
- **`scripts/prod/person/clear-folder-labels.sh` removes the backlog.** The tagger cannot: it
  writes one publisher key per format, while the release folder names LMS shows sit in ID3 `TPUB`
  (LMS reads that first) and the `__Free&None`s partly in a FLAC `LABEL` the tagger never writes.
  The script cleans every label key per format and the muma label rows, backs up first, supports
  `--rollback`, and asks LMS to rescan.

<!-- release notes -->

- **Folder names such as `__Free&None`, `__TODO` and whole release folder names no longer show up
  as labels.** New imports no longer get them; a one-off script removes the existing ones.
