- **The importer reads the release's `.nfo`, and the Deezer album it links, for what the folder name
  lacks.** A release no catalogue rule routes goes to the existing label folder its `.nfo` names
  (`Label`, `Company`) or its Deezer album names; a catalogue number the `.nfo` states is used when
  the name has none. Measured on the queue of 2026-10-02 the `.nfo` alone places 2.159 releases that
  were waiting for a label decision. Switch: `import_place_by_label_name` (Beheer > Configuratie,
  group Importer). Backlog releases placed this way are logged without a phone push.
- **Where your filing and the `.nfo` disagree, you choose once per label.** Releases whose `.nfo`
  says `Cloud 9 Music` sit in `Cloud 9 Dance`: such a release is not moved but proposed with both
  folders in Beheer > Labelvoorstellen, and the folder you confirm is remembered for every later
  release with that label (`rules_label_name_choices`, migrate_v56, seeded with the 104 labels found
  in the label tree on 2026-10-02; re-learn with `scripts/prod/person/learn-label-name-history.sh`).
- **Release dates follow a precision ladder** instead of stopping at the year: the Deezer release
  date, then an `.nfo` release/street date, the file's own full date, the `.nfo` rip date, and for a
  new release the day it arrived. The rung is written to `DATE_SOURCE`; a better rung later replaces
  a worse one, never the other way round. The UPC goes to `BARCODE`. Year-only dates sort below
  every dated track of their year in "recently released"; 22.689 EPs tracks of 2024-2026 had one.
- `scripts/prod/person/backfill-release-dates.sh` (dry run first) lifts the year-only tracks already
  in the label tree; about 7.550 of them link a Deezer album. New table `release_store_lookups`
  (migrate_v55). Design: `docs/designs/release-info-enrichment/`.

<!-- release notes -->

- **New releases land under their label more often and carry their real release date.** The
  importer reads the `.nfo` and the Deezer album it links; "recently released" stops listing
  yesterday's release after January's.
