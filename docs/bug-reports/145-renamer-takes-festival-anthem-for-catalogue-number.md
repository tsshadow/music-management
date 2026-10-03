# The Renamer Takes a Festival Anthem for a Catalogue Number

# status: fixed

# reported problem
Observed on production on 2026-10-02. The scene release
`Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG`
landed in `/mnt/music/EPs/__TODO` and was renamed to
`Official_Hardbass_2026_Anthem - Minus_Militia_And_Nolz_-_...`. The Mover then looked the
"catalogue number" `OfficialHardbass2026Anthem` up in `rules_catid_label`, found nothing, and the
release never reached a label folder, although its `.nfo` says `Company.: B2S` and the library has
`EPs/B2S`.

Related: folders whose name has no catalogue number at all were renamed with an empty prefix,
`__TODO/ - Guizcore_-_Coffee_Time-WEB-FLAC-2026`, `__TODO/ - Amigo_-_Uptempo_Fiesta_Vol.1-WEB-2026`.

Measured read-only on production on 2026-10-02:

- `__TODO` holds 6.583 folders: 2.663 start with ` - `, 1 with `- `, and 96 carry a word group the
  old rule took for a catalogue number -- every one a festival anthem
  (`Official_Harmony_Of_Hardcore_2026_Anthem`, `TIMELESS_FESTIVAL_2026_ANTHEM`, ...), an edit or
  remix marker (`2026_Remaster`, `Equal2_Remix`, `MI37_Extended_Rave_Mix`), `Volume_1`, prose
  (`I_Made_This_Song_In_1_Hour_While_I_Was_Pooping`), two `1 - ... (1)` duplicate-copy suffixes, or
  six `Cenobite_Digital_5x`.
- The importer's event log (`input:`/`parsed:` lines, 2026-09-17 to 2026-10-02, 597 distinct
  inputs): 164 renames to an empty prefix, 2 to a word prefix (Minus Militia and
  `BOMBSQUAD_And_Nolz_-_The_Awakening_(Official_Harmony_Of_Hardcore_2026_Anthem)_(Edit)`).

# Possible reason
`renamer.find_cat_id` took the last parenthesised group holding any digit, and when there was none
it still returned `' - ' + folder`. A year inside a festival anthem's name is a digit, and an empty
catalogue number is not a catalogue number. Both shapes route nowhere, and the empty one hides the
fact: the Mover reads `''` and records a proposal.

# solution
- `services/common/catalogue_number.py` decides what a catalogue number is, derived from the
  21.408 label folders whose prefix the old Renamer produced (it rejects none of them): 2-24
  characters; ASCII letters and digits in at most four parts joined by `.`, `_` or `-`; at least one
  digit; not a bare year; no part that is a title word (`Official`, `Anthem`, `Edit`, `Remix`,
  `Mix`, `Extended`, `Volume`, `Part`, ... also with digits glued on, `Anthem26`); and when there
  are several parts, every word in capitals (`GGM_RAW_001` yes, `Cenobite_Digital_52` no; a single
  part may mix case: `NOxEVO004`, `TOFF087d`).
- `find_cat_id` returns the last group that passes, or None, and the Renamer then leaves the name
  alone. It asks before the settle walk, so a folder that keeps its name costs nothing per cycle.
  `LabelPath.catalog_number` no longer returns a whole space-less scene name as the catalogue
  number of a release placed under its label without one.
- `services/importer/prefix_strip_repair.py` plus `scripts/prod/person/repair-word-prefixed-import-folders.sh`
  (dry run by default, backup, rename log, rollback, LMS notified, idempotent; not run): renames the
  misnamed folders to the name the Renamer gives them today. Planned against production's folder
  list, proposals and rules: 2.759 misnamed, 2.740 renameable (2.733 to their bare name, 5 to a
  catalogue number a rule routes, 2 to the number their own name carries), 19 refused because the
  bare name already exists (a second download of the same release). It ran on production on
  2026-10-02: 2.046 renamed.
- The same names also reached the label tree (`EPs/B2S/Official_Hardbass_2026_Anthem - ...`), where
  the tagger wrote the anthem into every file as its catalogue number.
  `services/importer/label_tree_prefix_repair.py`, run as `repair-word-prefixed-import-folders.sh
  --label-tree`, walks the label folders `ImportQueue.is_label_folder` accepts. It renames a
  release folder whose prefix holds a digit, is refused by the rule, and is exactly what the old
  Renamer took from the rest of the name. A refused prefix the old Renamer cannot have written,
  or one a `rules_catid_label` rule routes, is listed as AMBIGUOUS and never renamed. A prefix
  without a digit is a label code a person typed and stays. Per folder, in one transaction, the
  stored paths in `library_media_files` (with `file_path_hash`) and `tagger_processed_files` move
  along, so track ids and ratings stay. A `CATALOGNUMBER` tag that holds exactly the word is
  cleared, because the tagger never clears one. Dry run on production, 2026-10-03: 44.227 release
  folders, 19 to rename, 3 ambiguous (`I_Am_Frenchcore_05`, `I_Am_Frenchcore_12`, `NERKOLOG!K40`).
  Test: `test_importer_label_tree_prefix_repair.py`.
- Getting releases like Minus Militia to their label without a catalogue number is the
  enrichment in `docs/designs/release-info-enrichment/`.
- Tests: `services/importer/tests/test_importer_catalogue_number.py`,
  `test_importer_renamer.py`, `test_importer_prefix_strip_repair.py`, all on the production names.
